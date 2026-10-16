"""Read-only completeness review. Never a payment gate or automatic retry."""
from collections import defaultdict

SUMMARY_FIELDS = ("strength", "weakness", "practical_impact", "evidence_ref")
VAGUE = {"좋음", "보통", "충족", "부분 충족", "미흡", "정확함", "없음", "차이 있음"}


def summary_text(assessment):
    summary = (assessment or {}).get("summary") or {}
    labels = {"strength": "잘한 점", "weakness": "한계·보완", "practical_impact": "사용 시 영향",
              "evidence_ref": "근거"}
    parts = [f"{labels[k]}: {summary[k]}" for k in SUMMARY_FIELDS if summary.get(k)]
    if (assessment or {}).get('revision_reason'):
        parts.append('평가 정정: ' + assessment['revision_reason'])
    return "\n".join(parts)


def comparison_text(event):
    parts = [event.get("conclusion", "")]
    for key, label in (("common_ground", "공통 충족"), ("differences", "실제 차이"),
                       ("practical_impact", "사용 전 수정·적합한 상황")):
        if event.get(key):
            parts.append(f"{label}: {event[key]}")
    if event.get('revision_reason'):
        parts.append('비교 해설 정정: ' + event['revision_reason'])
    return "\n".join(parts)


def audit_session(doc):
    events = doc.get("events", [])
    reserves = {e["request_id"]: e for e in events if e["kind"] == "reserve"}
    results = {e["request_id"]: e for e in events if e["kind"] == "result"}
    assessments = {e["request_id"]: e for e in events if e["kind"] == "assessment"}
    comparisons = {(e["model_group"], e["case_id"]): e for e in events if e["kind"] == "comparison"}
    issues = []

    def issue(code, target, action):
        issues.append({"code": code, "target": target, "action": action})

    scope = doc.get("report_scope", {})
    if scope.get("origin") != "init_snapshot":
        issue("scope_missing", "run", "실행 계획 스냅샷 미확인; 전체 범위 완료로 표시하지 않음")
    coverage = []
    for model in scope.get("models", []):
        if not model.get("enabled", True):
            continue
        cases = model.get("case_ids", [c["id"] for c in doc["cases"]])
        missing = []
        for case in cases:
            for service in model.get("services", []):
                matches = [r for r in reserves.values() if r.get("candidate_id") == model["id"]
                           and r["case_id"] == case and r["service"] == service]
                if not any(r["request_id"] in results for r in matches):
                    missing.append(f"{service}/{case}")
        coverage.append({"model": model["id"], "expected": len(cases) * len(model.get("services", [])),
                         "missing": missing})
        if missing:
            issue("coverage_missing", model["id"], "미실측 칸 확인: " + ", ".join(missing))
    groups = defaultdict(list)
    for key, request in reserves.items():
        result = results.get(key)
        if result is None:
            issue("pending", key, "기존 대화·비용 대조 후 결과 저장; 재전송 금지")
            continue
        groups[(request.get("model_group") or request["model"], request["case_id"])].append(key)
        if result.get("status") != "success":
            continue
        if result.get("first_complete_observed_ms") is None:
            issue("timing_missing", key, "원시 시계가 있으면 대조; 없으면 미관측 유지. 유료 재전송 금지")
        assessment = assessments.get(key)
        if not assessment:
            issue("assessment_missing", key, "저장된 답변을 공통 기준으로 평가; UI 재요청 불필요")
            continue
        summary = assessment.get("summary") or {}
        absent = [k for k in SUMMARY_FIELDS if not isinstance(summary.get(k), str) or not summary[k].strip()]
        if absent:
            issue("answer_summary_missing", key, "실제 답변에서 잘한 점·한계·실무 영향·근거 보완: " + ", ".join(absent))
        for criterion in assessment.get("criteria", []):
            if any(str(criterion.get(k, "")).strip() in VAGUE for k in ("observation", "judgement")):
                issue("vague_assessment", key + "/" + criterion["criterion"], "좋음/충족 대신 실제 문구·검사 결과와 판단 이유 작성")
        if not result.get("answer_capture_verified"):
            issue("capture_unverified", key, "저장 원문과 UI 답변 끝/코드 본문을 대조; 추출 누락을 모델 오류로 채점하지 않음")
    for group, keys in groups.items():
        if len({reserves[k]["service"] for k in keys}) < 2:
            continue
        event = comparisons.get(group)
        if event is None:
            issue("comparison_missing", "/".join(group), "같은 질문 결과를 나란히 읽어 공통 충족·실제 차이·사용 전 수정 작성")
        else:
            cited = {o["request_id"] for o in event["observations"]}
            if set(keys) - cited:
                issue("comparison_coverage", "/".join(group), "누락 서비스 관찰 보완: " + ", ".join(sorted(set(keys) - cited)))
            if any(not str(event.get(k) or "").strip() for k in ("common_ground", "differences", "practical_impact")):
                issue("comparison_detail", "/".join(group), "결론 외 공통 충족·실제 차이·실무 영향 필드 보완")
    observed_ux = {e["service"] for e in events if e["kind"] == "ux"}
    for service in sorted({r["service"] for r in reserves.values()} - observed_ux):
        issue("ux_missing", service, "관측한 메뉴·가독성·복구 경험 기록; 못 본 내용은 미관측")
    successes = [r for r in results.values() if r.get("status") == "success"]
    return {"status": "review_needed" if issues else "record_checks_passed",
            "paid_requests": False, "automatic_retry": False, "coverage": coverage,
            "successes": len(successes),
            "timed": sum(r.get("first_complete_observed_ms") is not None for r in successes),
            "issues": issues,
            "notice": "기록 완결성 검사이며 실제 UI 진위·평가의 타당성·PDF/엑셀 시각 검증 통과를 뜻하지 않음"}


def audit_warnings(doc):
    result = audit_session(doc)
    counts = defaultdict(int)
    for item in result["issues"]:
        counts[item["code"]] += 1
    labels = {"scope_missing": "계획 미고정", "coverage_missing": "미완료 모델",
              "pending": "미확정 요청", "timing_missing": "시간 누락",
              "assessment_missing": "평가 누락", "answer_summary_missing": "답변별 상세 총평 누락",
              "vague_assessment": "추상적 평가", "capture_unverified": "원문 추출 대조 미확인",
              "comparison_missing": "질문별 비교 해설 누락", "comparison_coverage": "비교 해설 서비스 누락",
              "comparison_detail": "비교 해설 상세 항목 누락", "ux_missing": "UX 미관측"}
    return [f"보고서 검토: {labels[k]} {n}건. audit의 대상별 보완 목록을 확인하세요."
            for k, n in counts.items()]
