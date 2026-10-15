"""Question-by-question line charts; absent measurements remain gaps."""
import math
from pathlib import Path
from xml.sax.saxutils import escape

from .costs import converted_cost, krw_text
from .overview import report_groups, coverage_text, summaries, assessment_warnings

SERVICE_NAMES = {"monogpt": "MonoGPT", "timely": "Timely AI", "chatgpt": "ChatGPT"}
CASE_NAMES = {"education-01": "교육", "business-01": "기획", "summary-01": "요약",
              "calculation-01": "계산", "code-01": "코드", "image-01": "이미지",
              "file-01": "파일 분석", "file-generation-01": "파일 생성*"}
PALETTE = ["#507FEF", "#E35242", "#E7AC20", "#29A48B"]


def _observed_time(result):
    """Plot completion observation bounds, never invent an exact response time."""
    upper = result.get("first_complete_observed_ms")
    lower = result.get("last_generating_observed_ms")
    if result.get("status") != "success" or upper is None:
        return None, None, None
    upper = upper / 1000
    lower = lower / 1000 if lower is not None else None
    label = f"≤{upper:.1f}" if lower is None else f"{lower:.1f}–{upper:.1f}"
    return upper, lower, label


def chart_groups(rows, rates):
    """Align services by question ID, never by each service's row position."""
    groups = {}
    for item in rows:
        group = groups.setdefault(item["group"], {"cases": [], "services": {}})
        case = item["case"]["id"]
        if case not in group["cases"]:
            group["cases"].append(case)
        service = item["request"]["service"]
        series = group["services"].setdefault(service, {})
        if case in series:
            raise ValueError(f"그래프: {item['group']}/{service}/{case} 중복 최종 결과")
        charge = converted_cost(item["result"], service, rates)
        assessment = item["assessment"]
        quality = (sum(c["score"] for c in assessment["criteria"])
                   if assessment and item["result"].get("status") == "success" else None)
        upper, lower, time_label = _observed_time(item["result"])
        series[case] = {"cost": charge["krw"] if charge else None, "quality": quality,
                        "cost_status": item['result'].get('cost_status'),
                        "time": upper, "time_lower": lower, "time_label": time_label,
                        "model": item["request"]["model"], "reasoning": item["request"]["reasoning"],
                        "tier": item["request"]["comparison_tier"]}
    return groups


def _font():
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    font = "BenchmarkChartKorean"
    for candidate in ["/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
                      "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc", "C:/Windows/Fonts/malgun.ttf"]:
        if Path(candidate).is_file():
            try:
                pdfmetrics.registerFont(TTFont(font, candidate))
                return font
            except Exception:
                continue
    font = "HYSMyeongJo-Medium"
    pdfmetrics.registerFont(UnicodeCIDFont(font))
    return font


def _cost_ceiling(values):
    maximum = max((float(v) for v in values if v is not None), default=0)
    if maximum <= 0:
        return 1
    rough = maximum / 4
    magnitude = 10 ** math.floor(math.log10(rough))
    step = next(n * magnitude for n in (1, 2, 2.5, 5, 10) if n * magnitude >= rough)
    return math.ceil(maximum * 1.08 / step) * step


def _panel(cases, services, metric, font, height=185):
    from reportlab.graphics.shapes import Drawing, Line, String, Circle, Rect, Polygon
    from reportlab.lib import colors
    from reportlab.pdfbase import pdfmetrics
    width = 760
    drawing = Drawing(width, height)
    left, right, bottom, top = 53, 723, 27, height - 39
    heading = {"cost": "질문별 비용 (KRW · 원)", "quality": "질문별 답변 품질 (20점 만점)",
               "time": "질문별 소요시간 (초 · 완료 관측 상한/구간)"}[metric]
    drawing.add(String(left, height - 16, heading, fontName=font, fontSize=11, fillColor=colors.HexColor("#233C5A")))
    values = [series.get(case, {}).get(metric) for series in services.values() for case in cases]
    ceiling = 20 if metric == "quality" else _cost_ceiling(values)
    for tick in range(5):
        value = ceiling * tick / 4
        y = bottom + (top - bottom) * tick / 4
        drawing.add(Line(left, y, right, y, strokeColor=colors.HexColor("#DDE3EB"), strokeWidth=.6))
        drawing.add(String(left - 9, y - 3, f"{value:g}", textAnchor="end", fontName=font,
                           fontSize=8, fillColor=colors.HexColor("#68788B")))
    drawing.add(Line(left, bottom, right, bottom, strokeColor=colors.HexColor("#516176"), strokeWidth=.8))
    xs = [left + 28 + i * (right - left - 56) / max(1, len(cases) - 1) for i in range(len(cases))]
    if len(cases) == 1:
        xs = [(left + right) / 2]
    for x, case in zip(xs, cases):
        drawing.add(String(x, 7, CASE_NAMES.get(case, case), textAnchor="middle", fontName=font, fontSize=8))
    boxes = []
    leaders, labels = [], []
    missing = []
    for order, (service, series) in enumerate(services.items()):
        index = list(SERVICE_NAMES).index(service) if service in SERVICE_NAMES else order + 3
        color = colors.HexColor(PALETTE[index % len(PALETTE)])
        previous = None
        available = 0
        for x, case in zip(xs, cases):
            value = series.get(case, {}).get(metric)
            if value is None:
                previous = None  # A missing point must break the line.
                continue
            available += 1
            y = bottom + float(value) / ceiling * (top - bottom)
            low = series.get(case, {}).get("time_lower") if metric == "time" else None
            if low is not None:
                low_y = bottom + low / ceiling * (top - bottom)
                drawing.add(Line(x, low_y, x, y, strokeColor=color, strokeWidth=.6))
                drawing.add(Line(x - 3, low_y, x + 3, low_y, strokeColor=color, strokeWidth=.6))
                drawing.add(Line(x - 3, y, x + 3, y, strokeColor=color, strokeWidth=.6))
            if previous is not None:
                drawing.add(Line(previous[0], previous[1], x, y, strokeColor=color,
                                 strokeWidth=1.7, strokeDashArray=([5, 2] if index == 1 else
                                                               [2, 2] if index == 2 else None)))
            previous = (x, y)
            if index % 3 == 0:
                drawing.add(Circle(x, y, 2.9, fillColor=color, strokeColor=colors.white, strokeWidth=.5))
            elif index % 3 == 1:
                drawing.add(Rect(x - 3, y - 3, 6, 6, fillColor=color, strokeColor=colors.white, strokeWidth=.5))
            else:
                drawing.add(Polygon([x, y + 4, x + 4, y, x, y - 4, x - 4, y],
                                    fillColor=color, strokeColor=colors.white, strokeWidth=.5))
            label = (krw_text(value).removesuffix("원") if metric == "cost" else
                     series[case]["time_label"] if metric == "time" else str(value))
            text_width = pdfmetrics.stringWidth(label, font, 8)
            # Offset close/equal values so the labels remain readable.
            chosen = None
            for delta in (9, -15, 21, -27, 33, -39):
                ly = y + delta
                box = (x - text_width / 2 - 2, ly - 1, x + text_width / 2 + 2, ly + 9)
                if ly < bottom + 2 or ly > top + 14:
                    continue
                if not any(box[0] < b[2] and box[2] > b[0] and box[1] < b[3] and box[3] > b[1] for b in boxes):
                    chosen = (ly, box)
                    break
            if chosen:
                ly, box = chosen
                boxes.append(box)
                if abs(ly - y) > 12:
                    leaders.append(Line(x, y, x, ly + 4, strokeColor=colors.HexColor("#C7D0DC"), strokeWidth=.4))
                labels.append(Rect(box[0], box[1], box[2]-box[0], box[3]-box[1],
                                   fillColor=colors.white, strokeColor=None))
                labels.append(String(x, ly, label, textAnchor="middle", fontName=font, fontSize=8, fillColor=color))
        if available < len(cases):
            label = '비용 미노출' if metric == 'cost' and all(
                series.get(case, {}).get('cost_status') == 'unavailable' for case in cases) else '미측정'
            missing.append(f"{SERVICE_NAMES.get(service, service)} {len(cases)-available}개 {label}")
    # Labels must be above every series, not hidden by a later service's line.
    for shape in leaders + labels:
        drawing.add(shape)
    if missing:
        drawing.add(String(right, height - 16, " / ".join(missing), textAnchor="end", fontName=font,
                           fontSize=8, fillColor=colors.HexColor("#68788B")))
    return drawing


def write_chart_pdf(path, rows, today, name, rates, doc=None):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.graphics.shapes import Drawing, Line, String
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle
    font = _font()
    body = ParagraphStyle("chart-body", fontName=font, fontSize=8, leading=11, wordWrap="CJK")
    title = ParagraphStyle("chart-title", parent=body, fontSize=17, leading=22,
                           textColor=colors.HexColor("#233C5A"))
    def para(value):
        return Paragraph(escape(str(value)).replace("\n", "<br/>"), body)

    def table(data, widths):
        t = Table([[para(v) for v in row] for row in data], colWidths=widths, repeatRows=1)
        t.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#E9F0F8')),
                               ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                               ('TOPPADDING', (0, 0), (-1, -1), 5),
                               ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
                               ('LINEBELOW', (0, 0), (-1, -1), .4, colors.HexColor('#DDE3EB'))]))
        return t

    doc = doc or {"cases": list({r['case']['id']: r['case'] for r in rows}.values())}
    planned = report_groups(rows, doc)
    story = [Paragraph("모델별 비용·품질·시간 비교", title), Spacer(1, 12),
             para("모델별 비용·품질과 소요시간을 분리했습니다. 선의 각 점은 동일 질문의 관측값입니다. 미실측 모델은 결과를 만들지 않습니다.")]
    story.append(table([["모델", "진행 범위", "서비스", "질문 ID"]] +
                       [[g['label'], coverage_text(g), ', '.join(SERVICE_NAMES.get(s,s) for s in g['services']),
                         ', '.join(g['cases'])] for g in planned], [125, 210, 165, 260]))
    overview = [["모델", "서비스", "공통 n", "품질 평균 /20", "비용 합계(KRW)", "완료 관측 상한 중앙값"]]
    for g in planned:
        if not g['rows']:
            continue
        for s in summaries(g, rates):
            overview.append([g['label'], SERVICE_NAMES.get(s['service'],s['service']), s['n'],
                             s['quality'], s['cost'], s['time']])
    story.extend([Spacer(1, 12), para("동일 조건·공통 질문 교집합 요약 (파일 생성 제외, 속도 순위 아님)"),
                  table(overview, [140, 115, 65, 140, 140, 160])])
    warnings = assessment_warnings(rows)
    for warning in warnings[:3]:
        story.extend([Spacer(1, 6), para(warning)])
    if len(warnings) > 3:
        story.append(para(f"추가 평가 검토 {len(warnings)-3}건은 상세 PDF·엑셀을 확인하세요."))
    if doc.get('report_scope', {}).get('origin') != 'init_snapshot':
        story.append(para("실행 시작 시 계획이 고정되지 않아 현재 설정/기록으로 범위를 점검했습니다. 과거 승인 범위를 복원한 것은 아닙니다."))
    plotted = []
    for g in planned:
        # File tools may route to another model. Keep every such charge in the
        # function table below, never imply it is the selected model's cost.
        selected = [dict(r, group=g['label']) for r in g['rows']
                    if r['case']['id'] != 'file-generation-01' and r['result'].get('model_match') is not False]
        plotted.extend(selected)
    for group_name, group in chart_groups(plotted, rates).items():
        cases, services = group["cases"], group["services"]
        # Limit points per page to keep labels legible for larger question sets.
        for start in range(0, len(cases), 10):
            story.append(PageBreak())
            page_cases = cases[start:start + 10]
            part = f" · 질문 {start+1}–{start+len(page_cases)}" if len(cases) > 10 else ""
            story.append(Paragraph(escape(f"{group_name} · 비용과 답변 품질{part}"), title))
            legend = Drawing(760, 25)
            for order, service in enumerate(services):
                x = 53 + order * 170
                index = list(SERVICE_NAMES).index(service) if service in SERVICE_NAMES else order + 3
                color = colors.HexColor(PALETTE[index % len(PALETTE)])
                legend.add(Line(x, 11, x + 20, 11, strokeColor=color, strokeWidth=2))
                legend.add(String(x + 28, 7, SERVICE_NAMES.get(service, service), fontName=font, fontSize=10))
            story.extend([legend, _panel(page_cases, services, "cost", font), Spacer(1, 10),
                          _panel(page_cases, services, "quality", font)])
            conditions = []
            for service, series in services.items():
                entries = list(series.values())
                settings = list(dict.fromkeys(f"{v['model']} / {v['reasoning']}" for v in entries))
                rate = f" · 1크레딧={krw_text(rates[service])}" if service in rates else ""
                conditions.append(f"{SERVICE_NAMES.get(service, service)}: {', '.join(settings)}{rate}")
            story.append(Paragraph(escape(" | ".join(conditions)), body))
            note = ("가로축은 공통 질문 순서이며 미측정은 선을 끊습니다. 시간 점은 성공 답변의 최초 완료 관측 상한, "
                    "세로선은 마지막 생성 중~최초 완료 구간입니다. ≤는 상한만 관측한 경우입니다. "
                    "관측 간격이 넓으면 속도 순위를 단정하지 않습니다.")
            if any(v["tier"] == "exploratory" for s in services.values() for v in s.values()):
                note += " 탐색적 조건이 포함되어 있으며, 추론 설정이 다른 결과는 참고 비교입니다."
            story.append(Paragraph(escape(note), body))
            story.extend([PageBreak(), Paragraph(escape(f"{group_name} · 소요시간과 수치 대조{part}"), title),
                          legend, _panel(page_cases, services, "time", font, height=200)])
            matrix = [["질문", *[SERVICE_NAMES.get(s,s) for s in services]]]
            for case in page_cases:
                values = [CASE_NAMES.get(case, case)]
                for series in services.values():
                    point = series.get(case, {})
                    cost = krw_text(point['cost']) if point.get('cost') is not None else '비용 미확인'
                    quality = str(point['quality']) + '/20' if point.get('quality') is not None else '품질 미평가'
                    values.append(f"{cost} · {quality} · {point.get('time_label') or '시간 미관측'}초")
                matrix.append(values)
            story.append(table(matrix, [100] + [660 / len(services)] * len(services)))
            story.extend([Spacer(1, 8), para("시간 선의 점은 완료를 처음 확인한 상한입니다. 관측 구간이 겹치거나 넓으면 빠르다고 판정하지 않습니다. 파일 생성은 아래 별도 기능 결과에 포함합니다.")])
    function_rows = [r for r in rows if r['case']['id'] == 'file-generation-01' or r['result'].get('model_match') is False]
    if function_rows:
        story.extend([PageBreak(), Paragraph("파일 생성·모델 전환: 서비스 기능 결과", title),
                      para("선택 모델의 성능 평균·선그래프에서 분리했습니다. 실제 차감은 보존하며 파일 성공과 동일 모델 비교 가능성은 별개입니다.")])
        for row in function_rows:
            req, res = row['request'], row['result']
            charge = converted_cost(res, req['service'], rates)
            story.extend([Spacer(1, 14), para(f"{SERVICE_NAMES.get(req['service'],req['service'])} · 선택 {req['model']} / {req['reasoning']} · {krw_text(charge['krw']) if charge else '비용 미확인'}"),
                          para(f"기록 상태: {res.get('status')} · 실제 모델: {res.get('actual_model', '별도 필드 미기록; 아래 관측 근거 참조')}"),
                          para(res.get('limitations') or res.get('answer', '')[:650]),
                          para(res.get('evidence', '근거 미기록'))])

    def footer(canvas, doc):
        canvas.setFont(font, 8)
        canvas.setFillColor(colors.HexColor("#68788B"))
        canvas.drawString(40, 17, f"{today.isoformat()} · {name} · 사용자 입력 환산율 적용")
        canvas.drawRightString(landscape(A4)[0] - 40, 17, str(doc.page))

    SimpleDocTemplate(str(path), pagesize=landscape(A4), leftMargin=40, rightMargin=40,
                      topMargin=25, bottomMargin=30, title="질문별 비용·품질·소요시간 선그래프").build(
                          story, onFirstPage=footer, onLaterPages=footer)
