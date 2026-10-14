"""Offline private HTML report from the durable journal; no external assets."""
import html
from .session import read_session, session_dir


def escaped(value):
    return html.escape("미확인" if value is None else str(value), quote=True)


def report(root, name):
    doc = read_session(root, name)
    reservations = {e["request_id"]: e for e in doc["events"] if e["kind"] == "reserve"}
    results = {e["request_id"]: e for e in doc["events"] if e["kind"] == "result"}
    rows, details = [], []
    for key, request in reservations.items():
        result = results.get(key, {})
        lower, upper = result.get("last_generating_observed_ms"), result.get("first_complete_observed_ms")
        elapsed = "미확인" if upper is None else f"{(lower or 0)/1000:.2f}–{upper/1000:.2f}초 (관측 구간)"
        cells = [request["case_id"], request["service"], request["model"], request["reasoning"],
                 request["comparison_tier"], result.get("status", "전송 여부 대조 필요"), elapsed,
                 result.get("cost"), result.get("cost_unit"), result.get("cost_status"), result.get("quality_note", "미평가")]
        rows.append("<tr>" + "".join("<td>" + escaped(x) + "</td>" for x in cells) + "</tr>")
        details.append("<details><summary>" + escaped(key) + "</summary><h3>입력</h3><pre>" + escaped(request["prompt"])
                       + "</pre><h3>출력</h3><pre>" + escaped(result.get("answer")) + "</pre><p>" + escaped(result.get("limitations", "")) + "</p></details>")
    tested = {r["case_id"] for r in reservations.values()}
    pending = [c["id"] for c in doc["cases"] if c["id"] not in tested]
    headers = ["항목", "서비스", "표시 모델", "추론", "비교 범위", "상태", "완료 시간", "차감", "단위", "비용 근거", "평가"]
    content = """<!doctype html><html lang="ko"><meta charset="utf-8"><title>AI 서비스 비교 보고서</title>
<style>body{font:15px/1.6 system-ui,sans-serif;color:#17243b;margin:32px;max-width:1600px}h1{color:#153b6b}table{border-collapse:collapse;width:100%;font-size:13px}th,td{border:1px solid #ccd5df;padding:9px;text-align:left;vertical-align:top}th{background:#eaf0f8}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f5f7fa;padding:16px}details{margin:12px 0}aside{border-left:4px solid #d69317;padding:12px;background:#fff6df}@media print{details{display:block}table{font-size:10px}body{margin:10px}}</style>
<h1>AI 서비스 비교 보고서</h1><aside>화면에 표시된 모델·설정 기준의 서비스 경험 비교입니다. 실제 백엔드·시스템 프롬프트는 동일함을 보장하지 않습니다. 관측 시간은 정확한 생성 시간이 아니며, 서로 다른 크레딧은 직접 가격 비교하지 않습니다. 누락·미지원·미확정은 0점이나 무료가 아닙니다.</aside>"""
    content += "<p>예약 " + str(len(reservations)) + "건 · 결과 기록 " + str(len(results)) + "건</p>"
    content += "<p>미실행 항목: " + escaped(", ".join(pending) or "없음 (모델별 커버리지는 별도 확인)") + "</p>"
    content += "<div style='overflow:auto'><table><thead><tr>" + "".join("<th>" + x + "</th>" for x in headers) + "</tr></thead><tbody>" + "".join(rows) + "</tbody></table></div>"
    content += "<h2>원문 및 한계</h2>" + "".join(details)
    content += "<h2>정정·관찰</h2>" + "".join("<p>" + escaped(e["text"]) + "</p>" for e in doc["events"] if e["kind"] == "note") + "</html>"
    path = session_dir(root, name) / "report.html"
    path.write_text(content, encoding="utf-8")
    return {"report": str(path), "external_upload": False}
