"""Private, dated PDF/XLSX/chart export from the append-only execution journal."""
from datetime import date
from pathlib import Path
import os
import re
import tempfile
import zipfile
from xml.sax.saxutils import escape

from .costs import converted_cost, krw_text, normalize_rates
from .session import read_session, session_dir

SERVICE_NAMES = {"monogpt": "MonoGPT", "timely": "Timely AI", "chatgpt": "ChatGPT"}


def _text(value):
    return "미확인" if value is None or value == "" else str(value)


def _time(result):
    low, high = result.get("last_generating_observed_ms"), result.get("first_complete_observed_ms")
    if high is None:
        return "미관측"
    return (f"≤{high / 1000:.1f}초 (완료 관측 상한)" if low is None
            else f"{low / 1000:.1f}~{high / 1000:.1f}초 (관측 구간)")


def _cost(result, service, rates):
    if result.get("cost") is None:
        return "미노출" if result.get("cost_status") == "unavailable" else "미확정"
    return krw_text(converted_cost(result, service, rates)["krw"])


def _rows(doc):
    results = {e["request_id"]: e for e in doc["events"] if e["kind"] == "result"}
    assessments = {e["request_id"]: e for e in doc["events"] if e["kind"] == "assessment"}
    cases = {c["id"]: c for c in doc["cases"]}
    rows = []
    for request in (e for e in doc["events"] if e["kind"] == "reserve"):
        key = request["request_id"]
        result, assessment = results.get(key, {}), assessments.get(key)
        if result.get("status") == "success" and assessment is None:
            raise ValueError(f"{key}: 기준별 관찰·판단·근거가 없어 최종 보고서를 만들 수 없음")
        rows.append({"request": request, "result": result, "assessment": assessment,
                     "case": cases[request["case_id"]], "group": request.get("model_group") or request["model"]})
    return rows


def _literal(cell, value):
    # Copied answers beginning with '=' must never become spreadsheet formulas.
    cell.value = value[:32767] if isinstance(value, str) else value
    if isinstance(value, str):
        cell.data_type = "s"


def _cache_ledger_totals(path, totals, costs):
    """Cache evaluated score/cost formulas for previewers before Excel opens."""
    cached = path.with_suffix(".cached.xlsx")
    with zipfile.ZipFile(path) as source, zipfile.ZipFile(cached, "w") as target:
        for info in source.infolist():
            payload = source.read(info.filename)
            if info.filename == "xl/worksheets/sheet3.xml":
                for column, entries in (("I", totals), ("M", costs)):
                    for row_no, total in entries.items():
                        pattern = (rb'(<c r="' + column.encode() + str(row_no).encode() +
                                   rb'"[^>]*><f>.*?</f>)(?:<v\s*/>|<v></v>)')
                        payload, count = re.subn(pattern, lambda match: match[1] +
                                                 b"<v>" + str(total).encode() + b"</v>",
                                                 payload, count=1, flags=re.DOTALL)
                        if count != 1:
                            raise ValueError(f"수식 캐시 위치를 찾을 수 없음: {column}{row_no}")
            target.writestr(info, payload)
    os.replace(cached, path)


def _write_xlsx(path, rows, doc, today, name, rates):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    compare = wb.active
    compare.title = "서비스 비교"
    detail = wb.create_sheet("기준별 평가")
    ledger = wb.create_sheet("실측 원장")
    answers = wb.create_sheet("답변 원문")
    ux = wb.create_sheet("사용 경험")
    navy, stripe = "193B63", "F5F8FC"

    def setup(ws, labels, widths):
        ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(labels))
        ws.cell(1, 1, ws.title).font = Font(name="Arial", size=17, bold=True, color=navy)
        ws.row_dimensions[1].height = 32
        ws.cell(2, 1, f"생성일 {today.isoformat()} · 실행 {name} · UI 표시 조건 비교, 백엔드 동일성 미검증")
        ws.cell(2, 1).font = Font(name="Arial", size=10, color="52657A")
        ws.sheet_view.showGridLines = False
        ws.freeze_panes = "D5"
        for col, (label, width) in enumerate(zip(labels, widths), 1):
            cell = ws.cell(4, col, label)
            cell.fill = PatternFill("solid", fgColor=navy)
            cell.font = Font(name="Arial", size=10, bold=True, color="FFFFFF")
            cell.alignment = Alignment(vertical="center", wrap_text=True)
            ws.column_dimensions[get_column_letter(col)].width = width
        ws.row_dimensions[4].height = 32

    def add(ws, values, height=52):
        row_no = ws.max_row + 1
        for col, value in enumerate(values, 1):
            cell = ws.cell(row_no, col)
            _literal(cell, value)
            cell.font = Font(name="Arial", size=10, color="24364B")
            cell.alignment = Alignment(vertical="top", wrap_text=True)
            cell.border = Border(bottom=Side(style="thin", color="D9E2EC"))
            if row_no % 2 == 0:
                cell.fill = PatternFill("solid", fgColor=stripe)
        ws.row_dimensions[row_no].height = height
        return row_no

    services = list(SERVICE_NAMES) + list(dict.fromkeys(
        r["request"]["service"] for r in rows if r["request"]["service"] not in SERVICE_NAMES))
    setup(compare, ["모델 묶음", "질문 ID", *[SERVICE_NAMES.get(s, s) for s in services]],
          [26, 23, *([65] * len(services))])
    grouped = {}
    for row in rows:
        grouped.setdefault((row["group"], row["case"]["id"]), {})[row["request"]["service"]] = row
    for group in dict.fromkeys(row["group"] for row in rows):
        for case in doc["cases"]:
            grouped.setdefault((group, case["id"]), {})
    group_members = {}
    for row in rows:
        group_members.setdefault(row["group"], []).append(row)
    for (group, case_id), members in grouped.items():
        values = [group, case_id]
        for service in services:
            item = members.get(service)
            if item is None:
                exclusion = next((r["request"].get("excluded_services", {}).get(service)
                                  for r in group_members[group]
                                  if r["request"].get("excluded_services", {}).get(service)), None)
                values.append("모델 없음 — " + exclusion if exclusion else
                              "기록 없음 — 모델 없음으로 추정하지 않음")
                continue
            req, res, assessment = item["request"], item["result"], item["assessment"]
            score = f"{sum(x['score'] for x in assessment['criteria'])}/20" if assessment else "미평가"
            gaps = ([f"{x['criterion']}: {x['judgement']}" for x in assessment["criteria"] if x["score"] < 4]
                    if assessment else [])
            reason = gaps[:2] or ([assessment["criteria"][0]["observation"]] if assessment else [])
            values.append("\n".join([f"{req['model']} · 추론 {req['reasoning']}",
                                      f"품질 {score} · {_cost(res, req['service'], rates)} · {_time(res)}",
                                      f"상태 {_text(res.get('status'))}", *reason]))
        add(compare, values, 110)
    compare.auto_filter.ref = f"A4:{get_column_letter(2 + len(services))}{max(4, compare.max_row)}"
    compare.sheet_properties.pageSetUpPr.fitToPage = True
    compare.page_setup.fitToWidth = 1
    compare.page_setup.orientation = "landscape"

    setup(detail, ["요청 ID", "모델 묶음", "질문", "서비스", "평가 기준", "점수 /4",
                   "답변에서 확인한 사실", "판단·감점 이유", "근거 위치", "평가자", "블라인드"],
          [27, 23, 22, 18, 32, 10, 62, 62, 35, 19, 13])
    detail_ranges = {}
    for item in rows:
        assessment = item["assessment"]
        if assessment is None:
            continue
        first = detail.max_row + 1
        for criterion in assessment["criteria"]:
            row_no = add(detail, [item["request"]["request_id"], item["group"], item["case"]["id"],
                                  SERVICE_NAMES.get(item["request"]["service"], item["request"]["service"]),
                                  criterion["criterion"], criterion["score"], criterion["observation"],
                                  criterion["judgement"], criterion["evidence_ref"],
                                  assessment["evaluator"], "예" if assessment["blind"] else "아니오"], 75)
            if criterion["score"] < 4:
                detail.cell(row_no, 6).fill = PatternFill(
                    "solid", fgColor="FFF0D7" if criterion["score"] == 3 else "FCE4E2")
        detail_ranges[item["request"]["request_id"]] = (first, detail.max_row)
    detail.auto_filter.ref = f"A4:K{max(4, detail.max_row)}"

    setup(ledger, ["요청 ID", "모델 묶음", "질문", "서비스", "표시 모델", "추론", "비교 범위",
                   "상태", "품질 /20", "원시 차감(검증용)", "원시 단위", "환산율(원/단위)",
                   "비용(KRW)", "비용 근거", "시간 구간", "입력 SHA256", "제한·오류"],
          [27, 23, 22, 18, 30, 15, 18, 19, 13, 20, 16, 20, 17, 20, 34, 66, 50])
    totals, costs = {}, {}
    for item in rows:
        req, res = item["request"], item["result"]
        cost = converted_cost(res, req["service"], rates)
        row_no = add(ledger, [req["request_id"], item["group"], item["case"]["id"],
                              SERVICE_NAMES.get(req["service"], req["service"]), req["model"], req["reasoning"],
                              req["comparison_tier"], _text(res.get("status")), None,
                              float(cost["raw"]) if cost else None, res.get("cost_unit"),
                              float(cost["rate"]) if cost else None, None, res.get("cost_status"), _time(res),
                              req["prompt_sha256"], res.get("limitations")], 58)
        if cost:
            ledger.cell(row_no, 13, f"=J{row_no}*L{row_no}")
            ledger.cell(row_no, 13).number_format = '"₩"#,##0.00'
            ledger.cell(row_no, 13).font = Font(name="Arial", bold=True, color=navy)
            costs[row_no] = cost["krw"]
        if req["request_id"] in detail_ranges:
            first, last = detail_ranges[req["request_id"]]
            ledger.cell(row_no, 9, f"=SUM('기준별 평가'!F{first}:F{last})")
            ledger.cell(row_no, 9).font = Font(name="Arial", bold=True, color=navy)
            totals[row_no] = sum(c["score"] for c in item["assessment"]["criteria"])
    ledger.auto_filter.ref = f"A4:Q{max(4, ledger.max_row)}"

    setup(answers, ["요청 ID", "질문 ID", "서비스", "구간", "공통 질문 원문", "답변 원문"],
          [27, 23, 18, 10, 95, 115])
    for item in rows:
        req, res = item["request"], item["result"]
        answer = res.get("answer") or "미수집"
        for part, start in enumerate(range(0, len(answer), 30000), 1):
            add(answers, [req["request_id"], item["case"]["id"],
                          SERVICE_NAMES.get(req["service"], req["service"]), part,
                          req["prompt"] if part == 1 else "앞 행과 동일", answer[start:start + 30000]], 135)
    answers.auto_filter.ref = f"A4:F{max(4, answers.max_row)}"

    setup(ux, ["서비스", "관찰 대상", "실제 관찰", "화면·기록 근거"], [20, 35, 90, 65])
    for event in doc["events"]:
        if event["kind"] == "ux":
            for observation in event["observations"]:
                add(ux, [SERVICE_NAMES.get(event["service"], event["service"]),
                         observation["aspect"], observation["observation"], observation["evidence"]], 72)
    if ux.max_row == 4:
        add(ux, ["전체", "미관측", "UX 관측 기록이 없습니다.", "점수로 추정하지 않음"])
    ux.auto_filter.ref = f"A4:D{ux.max_row}"
    wb.calculation.fullCalcOnLoad = True
    wb.save(path)
    _cache_ledger_totals(path, totals, costs)
    with zipfile.ZipFile(path) as archive:
        if archive.testzip() is not None:
            raise ValueError("생성한 XLSX 압축 구조가 손상됨")


def _write_pdf(path, rows, doc, today, name, rates):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak

    font = "BenchmarkKorean"
    candidates = ["/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
                  "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc", "C:/Windows/Fonts/malgun.ttf"]
    for candidate in candidates:
        if Path(candidate).is_file():
            try:
                pdfmetrics.registerFont(TTFont(font, candidate))
                break
            except Exception:
                continue
    else:
        font = "HYSMyeongJo-Medium"
        pdfmetrics.registerFont(UnicodeCIDFont(font))
    ink, navy = colors.HexColor("#203047"), colors.HexColor("#193B63")
    body = ParagraphStyle("body", fontName=font, fontSize=9, leading=14, textColor=ink, wordWrap="CJK")
    small = ParagraphStyle("small", parent=body, fontSize=8, leading=12)
    heading = ParagraphStyle("heading", parent=body, fontSize=18, leading=26, textColor=navy, spaceAfter=12)
    sub = ParagraphStyle("sub", parent=body, fontSize=12, leading=19, textColor=navy,
                         spaceBefore=15, spaceAfter=7)

    def p(value, style=body):
        return Paragraph(escape(_text(value)).replace("\n", "<br/>"), style)

    def table(matrix, widths):
        result = Table([[p(value, small) for value in row] for row in matrix],
                       colWidths=widths, repeatRows=1, hAlign="LEFT")
        result.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E9F0F8")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("LINEBELOW", (0, 0), (-1, -1), .35, colors.HexColor("#D9E2EC")),
        ]))
        return result

    rates_label = ", ".join(f"{SERVICE_NAMES.get(service, service)} 1크레딧={krw_text(rate)}"
                            for service, rate in rates.items()) or "적용된 크레딧 환산율 없음"
    story = [p("AI 서비스 비교 보고서", heading),
             p(f"생성일 {today.isoformat()} · 실행 {name} · 결과 {len(rows)}건"),
             Spacer(1, 10), p("읽는 법", sub),
             p("표시 모델·추론·입력 조건의 서비스 경험 비교입니다. 실제 백엔드 동일성은 미검증입니다. "
               "품질은 질문별 5개 기준(각 0~4점)으로 평가하며 비용·속도·UX와 합산하지 않습니다. "
               "시간의 ≤는 완료 관측 상한만 확인했다는 뜻입니다. 비용은 사용자가 제공한 서비스별 원/크레딧 환산율을 적용한 원화입니다. "
               "환산율은 실제 결제액·할인·구독료와 다를 수 있습니다. 미노출·미확정은 0원이 아닙니다."),
             p("적용 환산율: " + rates_label, small),
             p("요약", sub)]
    summary = [["질문", "서비스", "표시 모델 · 추론", "상태 · 품질", "비용(KRW)", "시간"]]
    for item in rows:
        req, res, assessment = item["request"], item["result"], item["assessment"]
        score = f"{sum(c['score'] for c in assessment['criteria'])}/20" if assessment else "미평가"
        summary.append([item["case"]["id"], SERVICE_NAMES.get(req["service"], req["service"]),
                        req["model"] + " · " + req["reasoning"], _text(res.get("status")) + " · " + score,
                        _cost(res, req["service"], rates), _time(res)])
    groups = {}
    for item in rows:
        groups.setdefault((item["group"], item["case"]["id"]), {})[item["request"]["service"]] = item
    group_members = {}
    for item in rows:
        group_members.setdefault(item["group"], []).append(item)
    for group in group_members:
        for case in doc["cases"]:
            groups.setdefault((group, case["id"]), {})
    all_services = list(SERVICE_NAMES) + list(dict.fromkeys(
        item["request"]["service"] for item in rows if item["request"]["service"] not in SERVICE_NAMES))
    for (group, case_id), members in groups.items():
        for service in all_services:
            if service in members:
                continue
            exclusion = next((r["request"].get("excluded_services", {}).get(service)
                              for r in group_members[group]
                              if r["request"].get("excluded_services", {}).get(service)), None)
            summary.append([case_id, SERVICE_NAMES.get(service, service),
                            group + (" · 모델 없음" if exclusion else " · 미실측"),
                            exclusion or "기록 없음 — 모델 없음으로 추정하지 않음",
                            "해당 없음", "해당 없음"])
    story.append(table(summary, [72, 74, 135, 87, 75, 64]))
    story.extend([Spacer(1, 10),
                  p("각 판단의 실제 관찰·감점 이유는 아래에, 전체 답변 원문은 동봉한 엑셀에 있습니다.", small)])
    for item in rows:
        req, res, assessment = item["request"], item["result"], item["assessment"]
        story.extend([PageBreak(),
                      p(f"{item['group']} · {item['case']['id']} · {SERVICE_NAMES.get(req['service'], req['service'])}", heading),
                      p(f"{req['model']} / 추론 {req['reasoning']} / {_text(res.get('status'))} / "
                        f"{_cost(res, req['service'], rates)} / {_time(res)}"),
                      p("답변 평가", sub)])
        if assessment:
            story.append(p(f"평가자: {assessment['evaluator']} · 블라인드: {'예' if assessment['blind'] else '아니오'}", small))
            criteria = [["평가 기준", "점수", "확인한 사실과 위치", "판단·감점 이유"]]
            for c in assessment["criteria"]:
                criteria.append([c["criterion"], f"{c['score']}/4",
                                 c["observation"] + "\n근거: " + c["evidence_ref"], c["judgement"]])
            story.append(table(criteria, [111, 42, 176, 178]))
        else:
            story.append(p("성공 답변이 아니므로 품질 점수는 미평가. 실패·비용 상태는 별도로 유지합니다."))
        if res.get("limitations"):
            story.extend([p("제한과 오류", sub), p(res["limitations"])])
        story.extend([p("공통 질문", sub), p(req["prompt"], small)])
    story.extend([PageBreak(), p("사용 경험과 관찰", heading)])
    ux_events = [event for event in doc["events"] if event["kind"] == "ux"]
    if not ux_events:
        story.append(p("UX 관측 기록이 없어 평가하지 않았습니다."))
    for event in ux_events:
        story.append(p(SERVICE_NAMES.get(event["service"], event["service"]), sub))
        story.append(table([["관찰 대상", "실제 관찰", "근거"]] +
                           [[x["aspect"], x["observation"], x["evidence"]] for x in event["observations"]],
                           [100, 295, 112]))
    notes = [event["text"] for event in doc["events"] if event["kind"] == "note"]
    if notes:
        story.append(p("정정·한계", sub))
        story.extend(p(note) for note in notes)

    def footer(canvas, current):
        canvas.setFont(font, 8)
        canvas.setFillColor(colors.HexColor("#61738A"))
        canvas.drawString(44, 27, f"개인 비교 보고서 · {today.isoformat()} · {name}")
        canvas.drawRightString(A4[0] - 44, 27, str(current.page))

    SimpleDocTemplate(str(path), pagesize=A4, leftMargin=44, rightMargin=44,
                      topMargin=40, bottomMargin=43, title="AI 서비스 비교 보고서",
                      author="").build(story, onFirstPage=footer, onLaterPages=footer)
    if not path.read_bytes().startswith(b"%PDF"):
        raise ValueError("생성한 PDF 파일이 유효하지 않음")


def _write_chart_pdf(path, rows, today, name, rates):
    """One page per model group; separate scales avoid mixing points with won."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    from reportlab.graphics.shapes import Drawing, Rect, String
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak

    font = "BenchmarkChartKorean"
    candidates = ["/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
                  "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc", "C:/Windows/Fonts/malgun.ttf"]
    for candidate in candidates:
        if Path(candidate).is_file():
            try:
                pdfmetrics.registerFont(TTFont(font, candidate))
                break
            except Exception:
                continue
    else:
        font = "HYSMyeongJo-Medium"
        pdfmetrics.registerFont(UnicodeCIDFont(font))
    body = ParagraphStyle("chart-body", fontName=font, fontSize=9, leading=15, wordWrap="CJK")
    title = ParagraphStyle("chart-title", parent=body, fontSize=17, leading=25,
                           textColor=colors.HexColor("#193B63"))
    groups = {}
    for item in rows:
        groups.setdefault(item["group"], {}).setdefault(item["request"]["service"], []).append(item)
    story = []
    palette = {"monogpt": "#2764AD", "timely": "#24A58D", "chatgpt": "#E59B42"}
    for group_index, (group, services) in enumerate(groups.items()):
        if group_index:
            story.append(PageBreak())
        story.extend([
            Paragraph(escape(f"{group} · 서비스별 비용·품질"), title),
            Paragraph(escape(f"생성일 {today.isoformat()} · 실행 {name}"), body),
            Spacer(1, 13),
        ])
        metrics = []
        for service, items in services.items():
            scored = [item for item in items if item["result"].get("status") == "success"
                      and item["assessment"] is not None]
            scores = [sum(c["score"] for c in item["assessment"]["criteria"]) for item in scored]
            measured = [converted_cost(item["result"], service, rates) for item in items]
            measured = [cost["krw"] for cost in measured if cost is not None]
            metrics.append({"service": service, "scores": scores, "costs": measured,
                            "cases": sorted({item["case"]["id"] for item in items}),
                            "tiers": sorted({item["request"]["comparison_tier"] for item in items})})
        max_cost = max((float(sum(m["costs"]) / len(m["costs"]))
                        for m in metrics if m["costs"]), default=0)
        chart = Drawing(505, 115 + 112 * len(metrics))
        chart.add(String(8, chart.height - 18, "품질 평균 /20 · 성공 후 평가된 답변만", fontName=font,
                         fontSize=11, fillColor=colors.HexColor("#193B63")))
        top = chart.height - 54
        for index, metric in enumerate(metrics):
            y = top - index * 49
            label = SERVICE_NAMES.get(metric["service"], metric["service"])
            chart.add(String(8, y + 8, label[:20], fontName=font, fontSize=9))
            if metric["scores"]:
                average = sum(metric["scores"]) / len(metric["scores"])
                chart.add(Rect(134, y, 260 * average / 20, 17,
                               fillColor=colors.HexColor(palette.get(metric["service"], "#7A8DA4")), strokeColor=None))
                chart.add(String(405, y + 4, f"{average:.1f}/20  n={len(metric['scores'])}", fontName=font, fontSize=9))
            else:
                chart.add(String(134, y + 4, "미평가", fontName=font, fontSize=9))
        divider = top - 49 * len(metrics) - 5
        chart.add(String(8, divider, "평균 비용 KRW/요청 · 비용이 확정된 요청만", fontName=font,
                         fontSize=11, fillColor=colors.HexColor("#193B63")))
        for index, metric in enumerate(metrics):
            y = divider - 35 - index * 49
            label = SERVICE_NAMES.get(metric["service"], metric["service"])
            chart.add(String(8, y + 8, label[:20], fontName=font, fontSize=9))
            if metric["costs"]:
                average = sum(metric["costs"]) / len(metric["costs"])
                width = 260 * float(average) / max_cost if max_cost else 0
                chart.add(Rect(134, y, width, 17,
                               fillColor=colors.HexColor(palette.get(metric["service"], "#7A8DA4")), strokeColor=None))
                chart.add(String(405, y + 4, f"{krw_text(average)}  n={len(metric['costs'])}",
                                 fontName=font, fontSize=9))
            else:
                chart.add(String(134, y + 4, "비용 미확정", fontName=font, fontSize=9))
        story.extend([chart, Spacer(1, 8)])
        for metric in metrics:
            label = SERVICE_NAMES.get(metric["service"], metric["service"])
            cases = ", ".join(metric["cases"])
            rate_label = (f"1크레딧={krw_text(rates[metric['service']])}"
                          if metric["service"] in rates else "크레딧 환산율 미적용")
            story.append(Paragraph(escape(f"{label}: 기록 {len(metric['cases'])}개 질문 ({cases}); "
                                           f"비교 범위 {', '.join(metric['tiers'])}; {rate_label}"), body))
        story.append(Spacer(1, 10))
        story.append(Paragraph("품질과 비용은 서로 다른 축이며 합산 점수나 종합 순위가 아닙니다. "
                               "비용은 실패·미지원 요청도 차감이 확인되면 포함합니다. "
                               "미노출은 0원으로 취급하지 않습니다. 질문 구성·표본 수가 다르면 막대 길이만으로 우열을 판단하지 마세요. "
                               "환산율은 사용자 입력값이며 실제 청구액과 다를 수 있습니다.", body))
    SimpleDocTemplate(str(path), pagesize=A4, leftMargin=45, rightMargin=45,
                      topMargin=42, bottomMargin=42, title="서비스별 비용·품질 비교 그래프").build(story)
    if not path.read_bytes().startswith(b"%PDF"):
        raise ValueError("생성한 그래프 PDF 파일이 유효하지 않음")


def report(root, name, *, report_date=None, credit_rates=None):
    """Export a private dated report, workbook, and chart; never replace prior files."""
    today = date.fromisoformat(report_date) if report_date else date.today()
    rates = normalize_rates(credit_rates)
    doc = read_session(root, name)
    rows = _rows(doc)
    if not rows:
        raise ValueError("기록된 요청이 없어 최종 보고서를 만들 수 없음")
    # Validate every known charge before creating any final files.
    for item in rows:
        converted_cost(item["result"], item["request"]["service"], rates)
    folder = session_dir(root, name) / "final"
    folder.mkdir(exist_ok=True)
    stem = f"AI-service-comparison_{today.isoformat()}_{name}"
    pdf, xlsx, chart = (folder / f"{stem}.pdf", folder / f"{stem}.xlsx",
                        folder / f"{stem}_chart.pdf")
    if pdf.exists() or xlsx.exists() or chart.exists():
        raise FileExistsError("최종 파일이 이미 있습니다. 기존 파일을 확인하고 새 실행 ID를 사용하세요")
    try:
        with tempfile.TemporaryDirectory(dir=folder) as temporary:
            draft_pdf, draft_xlsx, draft_chart = (Path(temporary) / "draft.pdf",
                                                  Path(temporary) / "draft.xlsx",
                                                  Path(temporary) / "chart.pdf")
            _write_xlsx(draft_xlsx, rows, doc, today, name, rates)
            _write_pdf(draft_pdf, rows, doc, today, name, rates)
            _write_chart_pdf(draft_chart, rows, today, name, rates)
            os.replace(draft_xlsx, xlsx)
            os.replace(draft_pdf, pdf)
            os.replace(draft_chart, chart)
    except ImportError as exc:
        raise ValueError("PDF·XLSX 출력에는 requirements-report.txt 설치가 필요합니다") from exc
    return {"report": str(pdf), "workbook": str(xlsx), "chart": str(chart), "records": len(rows),
            "private": True, "external_upload": False}
