"""Question-by-question line charts; absent measurements remain gaps."""
import math
from pathlib import Path
from xml.sax.saxutils import escape

from .costs import converted_cost, krw_text

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
    return step * 4


def _panel(cases, services, metric, font):
    from reportlab.graphics.shapes import Drawing, Line, String, Circle, Rect, Polygon
    from reportlab.lib import colors
    from reportlab.pdfbase import pdfmetrics
    width, height = 760, 138
    drawing = Drawing(width, height)
    left, right, bottom, top = 53, 723, 24, 99
    heading = {"cost": "질문별 비용 (KRW · 원)", "quality": "질문별 답변 품질 (20점 만점)",
               "time": "질문별 소요시간 (초 · 완료 관측 상한/구간)"}[metric]
    drawing.add(String(left, 122, heading, fontName=font, fontSize=10, fillColor=colors.HexColor("#233C5A")))
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
            missing.append(f"{SERVICE_NAMES.get(service, service)} {len(cases)-available}개 미측정")
    # Labels must be above every series, not hidden by a later service's line.
    for shape in leaders + labels:
        drawing.add(shape)
    if missing:
        drawing.add(String(right, 122, " / ".join(missing), textAnchor="end", fontName=font,
                           fontSize=8, fillColor=colors.HexColor("#68788B")))
    return drawing


def write_chart_pdf(path, rows, today, name, rates):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.graphics.shapes import Drawing, Line, String
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak
    font = _font()
    body = ParagraphStyle("chart-body", fontName=font, fontSize=8, leading=11, wordWrap="CJK")
    title = ParagraphStyle("chart-title", parent=body, fontSize=17, leading=22,
                           textColor=colors.HexColor("#233C5A"))
    story = []
    for group_index, (group_name, group) in enumerate(chart_groups(rows, rates).items()):
        cases, services = group["cases"], group["services"]
        # Limit points per page to keep labels legible for larger question sets.
        for start in range(0, len(cases), 10):
            if story:
                story.append(PageBreak())
            page_cases = cases[start:start + 10]
            part = f" · 질문 {start+1}–{start+len(page_cases)}" if len(cases) > 10 else ""
            story.append(Paragraph(escape(f"{group_name} · 질문별 서비스 비교{part}"), title))
            legend = Drawing(760, 25)
            for order, service in enumerate(services):
                x = 53 + order * 170
                index = list(SERVICE_NAMES).index(service) if service in SERVICE_NAMES else order + 3
                color = colors.HexColor(PALETTE[index % len(PALETTE)])
                legend.add(Line(x, 11, x + 20, 11, strokeColor=color, strokeWidth=2))
                legend.add(String(x + 28, 7, SERVICE_NAMES.get(service, service), fontName=font, fontSize=10))
            story.extend([legend, _panel(page_cases, services, "cost", font), Spacer(1, 4),
                          _panel(page_cases, services, "quality", font), Spacer(1, 4),
                          _panel(page_cases, services, "time", font)])
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
            if "file-generation-01" in cases:
                note += " *파일 생성은 도구·라우팅이 개입하는 서비스 기능 평가입니다."
            story.append(Paragraph(escape(note), body))

    def footer(canvas, doc):
        canvas.setFont(font, 8)
        canvas.setFillColor(colors.HexColor("#68788B"))
        canvas.drawString(40, 17, f"{today.isoformat()} · {name} · 사용자 입력 환산율 적용")
        canvas.drawRightString(landscape(A4)[0] - 40, 17, str(doc.page))

    SimpleDocTemplate(str(path), pagesize=landscape(A4), leftMargin=40, rightMargin=40,
                      topMargin=25, bottomMargin=30, title="질문별 비용·품질·소요시간 선그래프").build(
                          story, onFirstPage=footer, onLaterPages=footer)
