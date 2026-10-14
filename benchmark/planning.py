"""Fail-closed offline preflight. Never logs into a service or sends a prompt."""

import hashlib
import json
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.parse import urlsplit


def project_path(root, relative):
    root = Path(root).resolve()
    if not isinstance(relative, str) or Path(relative).is_absolute():
        raise ValueError("프로젝트 상대 경로가 필요합니다")
    path = (root / relative).resolve()
    try:
        path.relative_to(root)
    except ValueError:
        raise ValueError("프로젝트 외부 경로는 허용하지 않습니다")
    return path


def read_json(root, relative):
    return json.loads(project_path(root, relative).read_text(encoding="utf-8"))


def digest(value):
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def index_items(items):
    result = {}
    for item in items:
        key = item["id"]
        if not isinstance(key, str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]*", key):
            raise ValueError("ID는 소문자 영숫자와 하이픈만 사용하세요")
        if key in result:
            raise ValueError("중복 ID: " + key)
        result[key] = item
    return result


def positive_decimal(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        number = Decimal(str(value))
    except InvalidOperation:
        return None
    return number if number.is_finite() and number > 0 else None


def known(value):
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip()) and value.lower() not in {"unknown", "auto", "pending"}
    if isinstance(value, dict):
        return all(known(v) for v in value.values())
    if isinstance(value, list):
        return all(known(v) for v in value)
    return True


def build_plan(root, config_path="config/benchmark.json"):
    config = read_json(root, config_path)
    if config.get("schema_version") != 1:
        raise ValueError("지원하지 않는 설정 버전")
    case_doc = read_json(root, config["case_file"])
    fixture_doc = read_json(root, config["fixture_manifest"])
    all_cases = index_items(case_doc["cases"])
    fixtures = index_items(fixture_doc["fixtures"])
    all_models = index_items(config["models"])
    cases = [v for v in all_cases.values() if v.get("enabled") is True]
    models = [v for v in all_models.values() if v.get("enabled") is True]
    services = config["services"]
    if len(services) < 2 or len(set(services)) != len(services):
        raise ValueError("서로 다른 서비스 2개 이상이 필요합니다")
    index_items([{"id": service} for service in services])
    fixture_services = {service for model in models for service in model.get("services", services)}
    repetitions = config["repetitions"]
    if type(repetitions) is not int or repetitions < 1:
        raise ValueError("반복 횟수는 1 이상의 정수여야 합니다")
    limit = config["max_total_requests"]
    if type(limit) is not int or limit < 1:
        raise ValueError("요청 상한은 1 이상의 정수여야 합니다")
    blockers, warnings, inputs = [], [], []
    if config.get("auto_top_up") is not False:
        blockers.append("자동 충전은 false로 설정해야 합니다")
    if not cases or not models:
        blockers.append("활성 테스트와 모델이 각각 하나 이상 필요합니다")
    budget = positive_decimal(config.get("budget_krw_per_service"))
    if budget is None:
        blockers.append("서비스별 원화 예산 상한 미설정")
    for case in cases:
        turns = case["turns"]
        if not turns or any(not isinstance(turn, str) or not turn.strip() for turn in turns):
            raise ValueError("빈 프롬프트: " + case["id"])
        if case.get("expected") is None or not case.get("rubric"):
            blockers.append(case["id"] + ": 정답·검증 기준 미준비")
        hashes = []
        for fixture_id in case["fixture_ids"]:
            fixture = fixtures.get(fixture_id)
            if not fixture:
                blockers.append(case["id"] + ": 파일 미등록 " + fixture_id)
                continue
            if (fixture.get("classification") not in {"public", "nonpersonal_work"}
                    or fixture.get("review_status") != "approved" or not fixture.get("review_note")):
                blockers.append(fixture_id + ": 비개인 자료 검토 미완료")
            if not fixture_services.issubset(set(fixture.get("allowed_services", []))):
                blockers.append(fixture_id + ": 업로드 대상 미확인")
            path = project_path(root, fixture["path"])
            if not path.is_file():
                blockers.append(fixture_id + ": 파일 없음")
                continue
            sha = hashlib.sha256(path.read_bytes()).hexdigest()
            if sha != fixture.get("sha256"):
                blockers.append(fixture_id + ": 파일 해시 불일치, 재검토 필요")
            hashes.append({"id": fixture_id, "sha256": sha})
        inputs.append({"case_id": case["id"], "turn_count": len(turns),
                       "input_sha256": digest({"turns": turns, "files": hashes}),
                       "turn_sha256": [hashlib.sha256(t.encode("utf-8")).hexdigest() for t in turns],
                       "files": hashes})
    turns_per_repeat = sum(len(c["turns"]) for c in cases)
    requests_per_model_service = repetitions * turns_per_repeat
    groups = {}
    exclusions = {}
    for model in models:
        members = model.get("services", services)
        if (not isinstance(members, list) or len(members) < 2
                or len(set(members)) != len(members)
                or not set(members).issubset(set(services))):
            raise ValueError(model["id"] + ": 비교 그룹은 등록된 서로 다른 서비스 2개 이상이어야 합니다")
        omitted = set(services) - set(members)
        reasons = model.get("excluded_services", {})
        if not isinstance(reasons, dict) or set(reasons) != omitted:
            raise ValueError(model["id"] + ": 제외 서비스마다 명시적 사유가 필요합니다")
        if any(not isinstance(v, str) or not v.strip() for v in reasons.values()):
            raise ValueError(model["id"] + ": 빈 제외 사유는 허용하지 않습니다")
        groups[model["id"]] = members
        exclusions[model["id"]] = reasons
    participating = {s for members in groups.values() for s in members}
    request_count = sum(len(members) for members in groups.values()) * requests_per_model_service
    if request_count > limit:
        blockers.append("총 요청 상한 초과")
    if repetitions == 1:
        warnings.append("각 테스트 1회: 반복 변동성과 통계적 순위는 판단할 수 없음")
    profiles = {service: read_json(root, "sites/" + service + ".json") for service in services}
    estimated_cost = {service: Decimal(0) for service in services}
    cost_complete = {service: True for service in services}
    comparison_groups = []
    for service, profile in profiles.items():
        if service not in participating:
            continue
        url = urlsplit(profile.get("url") or "")
        if url.scheme != "https" or not url.hostname or url.username or url.password:
            blockers.append(service + ": 유효한 HTTPS 사이트 URL 미설정")
        if profile.get("id") != service or profile.get("browser_flow_verified") is not True:
            blockers.append(service + ": 실제 UI 흐름 미검증")
        if profile.get("credit_observation", {}).get("status") != "verified":
            blockers.append(service + ": 크레딧 관측 방법 미검증")
        for case in cases:
            if not set(case["requires"]).issubset(set(profile.get("capabilities", []))):
                blockers.append(service + "/" + case["id"] + ": 요구 기능 미확인")
    for model in models:
        signatures = []
        evidence = []
        for service, profile in profiles.items():
            if service not in groups[model["id"]]:
                continue
            resolved = profile.get("models", {}).get(model["id"], {})
            reasoning = resolved.get("reasoning", {})
            valid_reasoning = (isinstance(reasoning, dict)
                               and set(reasoning) == {"mode", "level", "budget_tokens"}
                               and known(reasoning.get("mode")) and known(reasoning.get("level"))
                               and (reasoning["budget_tokens"] is None or
                                    (type(reasoning["budget_tokens"]) is int and reasoning["budget_tokens"] >= 0)))
            feature_settings = resolved.get("feature_settings")
            if (resolved.get("verified") is not True
                    or not known(resolved.get("canonical_model")) or not known(resolved.get("version"))
                    or not valid_reasoning or not isinstance(feature_settings, dict)
                    or not feature_settings or not known(feature_settings)
                    or not resolved.get("evidence")
                    or resolved.get("evidence_scope") not in {"ui_declared", "provider_documented"}):
                blockers.append(service + "/" + model["id"] + ": 모델·버전·추론·설정 근거 미확인")
            else:
                signatures.append(digest({k: resolved[k] for k in
                                          ("canonical_model", "version", "reasoning", "feature_settings")}))
                evidence.append({"service": service, "scope": resolved["evidence_scope"],
                                 "reference": resolved["evidence"]})
                if resolved["evidence_scope"] == "ui_declared":
                    warnings.append(service + "/" + model["id"] + ": UI 선언만 확인, 실제 백엔드 버전 미검증")
            max_cost = positive_decimal(resolved.get("max_request_cost_krw"))
            if max_cost is None:
                blockers.append(service + "/" + model["id"] + ": 요청당 보수적 비용 상한 미확정")
                cost_complete[service] = False
            else:
                estimated_cost[service] += max_cost * requests_per_model_service
        if len(set(signatures)) > 1:
            blockers.append(model["id"] + ": 사이트 간 모델·버전·추론·설정 불일치")
        comparison_groups.append({"candidate_id": model["id"], "requested_name": model["requested_name"],
                                  "services": groups[model["id"]],
                                  "excluded_services": exclusions[model["id"]],
                                  "conditions_match": len(signatures) == len(groups[model["id"]]) and len(set(signatures)) == 1,
                                  "evidence": evidence})
    for service in services:
        if budget is not None and estimated_cost[service] > budget:
            blockers.append(service + ": 계획 비용 상한이 서비스 예산 초과")
    return {
        "status": "blocked" if blockers else "ready_for_implementation",
        "live_execution_implemented": False,
        "requests_planned": request_count,
        "planned_cost_upper_bound_krw": {s: str(estimated_cost[s]) if cost_complete[s] else None for s in services},
        "config_sha256": digest(config), "cases_sha256": digest(case_doc),
        "profiles_sha256": digest(profiles), "fixture_manifest_sha256": digest(fixture_doc),
        "comparison_groups": comparison_groups, "inputs": inputs,
        "blockers": blockers, "warnings": warnings,
    }
