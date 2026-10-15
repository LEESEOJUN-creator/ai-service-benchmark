"""Shared report coverage and like-for-like descriptive summaries (no rankings)."""
from statistics import mean, median

from .costs import converted_cost, krw_text

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
    return f"{state} · {len(completed)}/{target}칸 (성공·실패 포함)"


def model_eligible(item):
    return (item["case"]["id"] != "file-generation-01"
            and item["result"].get("status") == "success"
            and item["result"].get("model_match") is not False
            and item["request"].get("comparison_tier") == "ui_matched"
            and item["assessment"] is not None)


def summaries(group, rates):
    """All participating services use the same eligible question intersection."""
    services = group["services"]
    eligible = {s: {r["case"]["id"]: r for r in group["rows"]
                    if r["request"]["service"] == s and model_eligible(r)} for s in services}
    common = set.intersection(*(set(v) for v in eligible.values())) if eligible else set()
    output = []
    for service in services:
        items = [eligible[service][case] for case in group["cases"] if case in common]
        scores = [sum(c["score"] for c in r["assessment"]["criteria"]) for r in items]
        costs = [converted_cost(r["result"], service, rates) for r in items]
        times = [r["result"].get("first_complete_observed_ms") for r in items]
        notes = []
        for r in items:
            for c in r["assessment"]["criteria"]:
                if c["score"] < 4:
                    notes.append(f"{r['case']['id']} / {c['criterion']}: {c['observation']} → {c['judgement']} ({c['evidence_ref']})")
        if not notes and items:
            c = items[0]["assessment"]["criteria"][0]
            notes.append(f"{items[0]['case']['id']}: {c['observation']} ({c['evidence_ref']})")
        output.append({"service": service, "n": len(items),
                       "quality": f"{mean(scores):.2f}/20" if scores else "비교 가능한 공통 평가 없음",
                       "cost": krw_text(sum(c["krw"] for c in costs)) if costs and all(costs) else "미확인",
                       "time": f"≤{median(times)/1000:.1f}초" if times and all(t is not None for t in times) else "미관측",
                       "perfect": f"{scores.count(20)}/{len(scores)}",
                       "evidence": "\n".join(notes[:3]) or "실측 또는 동일 조건 근거 없음"})
    return output


def assessment_warnings(rows):
    warnings = []
    vague = {"부분 충족", "충족", "좋음", "보통", "미흡", "정확함"}
    for row in rows:
        for c in (row["assessment"] or {}).get("criteria", []):
            if c["judgement"].strip() in vague or "길 수 있음" in c["judgement"]:
                warnings.append(f"{row['request']['request_id']} / {c['criterion']}: 판단 근거 보완 필요 — {c['judgement']}")
    scores = [sum(c["score"] for c in r["assessment"]["criteria"]) for r in rows if r["assessment"]]
    if scores and scores.count(20) / len(scores) >= .7:
        warnings.insert(0, f"만점 {scores.count(20)}/{len(scores)}건: 현재 기준에서 차이가 작습니다. 점수를 억지로 벌리지 말고 실제 제안·구성·누락의 차이를 확인하세요.")
    return warnings
