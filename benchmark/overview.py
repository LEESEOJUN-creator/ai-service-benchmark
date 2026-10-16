"""Shared report coverage and like-for-like descriptive summaries (no rankings)."""
from statistics import mean, median

from .costs import converted_cost, krw_text
from .audit import summary_text

SERVICE_NAMES = {"monogpt": "MonoGPT", "timely": "Timely AI", "chatgpt": "ChatGPT"}


def report_groups(rows, doc):
    """Keep unmeasured candidates visible; only exact IDs/labels join records."""
    scope = doc.get("report_scope", {})
    groups, assigned = [], set()
    for model in scope.get("models", []):
        label = model.get("report_label", model["requested_name"])
        members = [r for r in rows if r["request"].get("candidate_id") == model["id"]
                   or (not r["request"].get("candidate_id") and r["group"] == label)]
        assigned.update(id(r) for r in members)
        groups.append({"label": label, "rows": members,
                       "services": model.get("services", list(SERVICE_NAMES)),
                       "cases": model.get("case_ids", [c["id"] for c in doc["cases"]]),
                       "enabled": model.get("enabled", True),
                       "excluded": model.get("excluded_services", {})})
    for label in dict.fromkeys(r["group"] for r in rows if id(r) not in assigned):
        members = [r for r in rows if id(r) not in assigned and r["group"] == label]
        groups.append({"label": label, "rows": members,
                       "services": list(dict.fromkeys(r["request"]["service"] for r in members)),
                       "cases": [c["id"] for c in doc["cases"]], "enabled": True, "excluded": {}})
    return groups


def coverage_text(group):
    selected = set(group["cases"])
    completed = {(r["request"]["service"], r["case"]["id"]) for r in group["rows"]
                 if r["result"].get("status") and r["case"]["id"] in selected
                 and r["request"]["service"] in group["services"]}
    target = len(selected) * len(group["services"])
    state = "결과 기록 완료" if len(completed) == target else "부분 실측" if completed else "미실측"
    if not group["enabled"]:
        state += " · 설정 비활성"
    missing = sum(r['result'].get('status') == 'success' and r['result'].get('first_complete_observed_ms') is None
                  for r in group['rows'])
    if missing:
        state += f" · 시간 측정 미완료 {missing}건"
    if any(r['request'].get('comparison_tier') == 'exploratory' for r in group['rows']):
        state += " · 참고 비교(추론 차이)"
    return f"{state} · {len(completed)}/{target}칸 (성공·실패 포함)"


def model_eligible(item, tier="ui_matched"):
    return (item["case"]["id"] != "file-generation-01"
            and item["result"].get("status") == "success"
            and item["result"].get("model_match") is not False
            and item["request"].get("comparison_tier") == tier
            and item["assessment"] is not None)


def summaries(group, rates):
    """All participating services use the same eligible question intersection."""
    services = group["services"]
    # A wholly exploratory group gets its own clearly labeled descriptive summary.
    # Never merge exploratory rows into a strict common-question mean.
    exploratory = bool(group['rows']) and all(r['request'].get('comparison_tier') == 'exploratory' for r in group['rows'])
    tier = 'exploratory' if exploratory else 'ui_matched'
    eligible = {s: {r["case"]["id"]: r for r in group["rows"]
                    if r["request"]["service"] == s and model_eligible(r, tier)} for s in services}
    common = set.intersection(*(set(v) for v in eligible.values())) if eligible else set()
    output = []
    for service in services:
        items = [eligible[service][case] for case in group["cases"] if case in common]
        scores = [sum(c["score"] for c in r["assessment"]["criteria"]) for r in items]
        costs = [converted_cost(r["result"], service, rates) for r in items]
        times = [r["result"].get("first_complete_observed_ms") for r in items]
        notes = []
        if exploratory:
            notes.append("참고 비교: 사이트별 추론 설정이 다르거나 미공개입니다. 동일 조건 성능 순위가 아닙니다.")
        for r in items:
            if summary_text(r['assessment']):
                notes.append(f"{r['case']['id']}: {summary_text(r['assessment'])}")
            else:
                criteria = [c for c in r['assessment']['criteria'] if c['score'] < 4]
                if criteria:
                    c = criteria[0]
                    notes.append(f"{r['case']['id']} / {c['criterion']}: {c['observation']} → {c['judgement']} ({c['evidence_ref']})")
        if not notes and items:
            c = items[0]["assessment"]["criteria"][0]
            notes.append(f"{items[0]['case']['id']}: {c['observation']} ({c['evidence_ref']})")
        output.append({"service": service, "n": len(items),
                       "quality": (f"{mean(scores):.2f}/20" + (" (참고)" if exploratory else "")) if scores else "비교 가능한 공통 평가 없음",
                       "cost": krw_text(sum(c["krw"] for c in costs)) if costs and all(costs) else "미확인",
                       "time": f"≤{median(times)/1000:.1f}초" if times and all(t is not None for t in times) else "미관측",
                       "perfect": f"{scores.count(20)}/{len(scores)}",
                       "evidence": "\n".join(notes[:3]) or "실측 또는 동일 조건 근거 없음"})
    return output


def assessment_warnings(rows):
    warnings = []
    missing = [r for r in rows if r['result'].get('status') == 'success'
               and r['result'].get('first_complete_observed_ms') is None]
    if missing:
        warnings.append(f"시간 측정 미완료: 성공 답변 {len(missing)}건에 완료 관측 시간이 없습니다. 전체 실측 완료/속도 순위로 해석하지 마세요. 재전송 없이 원기록을 확인하세요.")
    vague = {"부분 충족", "충족", "좋음", "보통", "미흡", "정확함"}
    for row in rows:
        for c in (row["assessment"] or {}).get("criteria", []):
            if c["judgement"].strip() in vague or "길 수 있음" in c["judgement"]:
                warnings.append(f"{row['request']['request_id']} / {c['criterion']}: 판단 근거 보완 필요 — {c['judgement']}")
    scores = [sum(c["score"] for c in r["assessment"]["criteria"]) for r in rows if r["assessment"]]
    if scores and scores.count(20) / len(scores) >= .7:
        warnings.insert(0, f"만점 {scores.count(20)}/{len(scores)}건: 현재 기준에서 차이가 작습니다. 점수를 억지로 벌리지 말고 실제 제안·구성·누락의 차이를 확인하세요.")
    return warnings
