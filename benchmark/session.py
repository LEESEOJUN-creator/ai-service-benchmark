"""Private, append-only execution journal. It never opens a browser or sends data.

The browser agent owns UI verification; this module prevents silent replays and
keeps unmeasured fields distinct from zero. One journal writer at a time.
"""
import hashlib
import json
import os
import re
from pathlib import Path

from .planning import project_path, read_json


def session_dir(root, name):
    if not re.fullmatch(r"[a-z][a-z0-9-]{0,63}", name):
        raise ValueError("run ID: 소문자 시작, 영숫자·하이픈 최대 64자")
    path = project_path(root, "runs/" + name)
    if not path.is_relative_to(Path(root).resolve() / "runs"):
        raise ValueError("runs 밖에는 결과를 저장하지 않습니다")
    return path


def initialize(root, name, case_file="cases/core.json", config_file="config/benchmark.json"):
    folder = session_dir(root, name)
    folder.mkdir(parents=True, exist_ok=True)
    cases = read_json(root, case_file)
    # No accounts or credentials. All eight prompts are frozen even when gated.
    payload = {"schema_version": 1, "cases": cases["cases"], "events": []}
    if project_path(root, config_file).is_file():
        config = read_json(root, config_file)
        payload["report_scope"] = {"models": config["models"], "origin": "init_snapshot"}
    with (folder / "session.json").open("x", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
    return {"status": "created", "path": str(folder), "browser_execution": False}


def read_session(root, name):
    path = session_dir(root, name) / "session.json"
    return json.loads(path.read_text(encoding="utf-8"))


def append_event(root, name, event):
    folder = session_dir(root, name)
    lock = folder / ".writer.lock"
    fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        doc = read_session(root, name)
        validate_event(doc, event)
        if event.get("kind") == "reserve":
            for fixture in event.get("fixtures", {}).values():
                path = project_path(root, fixture.get("path", ""))
                if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != fixture["sha256"]:
                    raise ValueError("첨부 직전 파일 바이트/경로 불일치")
        event = dict(event, sequence=len(doc["events"]) + 1)
        doc["events"].append(event)
        temporary = folder / ".session.tmp"
        with temporary.open("w", encoding="utf-8") as handle:
            json.dump(doc, handle, ensure_ascii=False, indent=2, allow_nan=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, folder / "session.json")
        return event
    finally:
        os.close(fd)
        lock.unlink()


def validate_event(doc, event):
    kind = event.get("kind")
    if kind not in {"reserve", "result", "assessment", "comparison", "ux", "note"}:
        raise ValueError("kind: reserve/result/assessment/comparison/ux/note")
    if kind == "comparison":
        for field in ("model_group", "case_id", "conclusion"):
            if not isinstance(event.get(field), str) or not event[field].strip():
                raise ValueError("비교 해설에 모델 묶음·질문·결론 필요")
        observations = event.get("observations")
        if not isinstance(observations, list) or len(observations) < 2:
            raise ValueError("비교 해설은 두 서비스 이상의 실제 관찰 필요")
        seen = set()
        for item in observations:
            if not isinstance(item, dict) or any(not isinstance(item.get(f), str) or not item[f].strip()
                                                for f in ("request_id", "observation", "evidence_ref")):
                raise ValueError("비교 해설의 요청·관찰·근거 필요")
            reserve = next((e for e in doc['events'] if e['kind'] == 'reserve'
                            and e['request_id'] == item['request_id']), None)
            if (reserve is None or reserve['case_id'] != event['case_id']
                    or (reserve.get('model_group') or reserve['model']) != event['model_group']
                    or not any(e['kind'] == 'result' and e['request_id'] == item['request_id'] for e in doc['events'])):
                raise ValueError("비교 해설은 같은 묶음·질문의 실제 결과를 참조해야 합니다")
            if reserve['service'] in seen:
                raise ValueError("비교 해설 서비스 중복")
            seen.add(reserve['service'])
        if any(e['kind'] == 'comparison' and e['model_group'] == event['model_group']
               and e['case_id'] == event['case_id'] for e in doc['events']):
            raise ValueError("비교 해설 덮어쓰기 금지; 정정 note 사용")
        return
    if kind == "note":
        if not isinstance(event.get("text"), str) or not event["text"].strip():
            raise ValueError("빈 note")
        return
    if kind == "ux":
        if event.get("service") not in {"monogpt", "timely", "chatgpt"}:
            raise ValueError("검증된 서비스 ID 필요")
        observations = event.get("observations")
        if not isinstance(observations, list) or not observations:
            raise ValueError("UX 관측 항목 필요")
        for item in observations:
            if not isinstance(item, dict) or any(
                not isinstance(item.get(field), str) or not item[field].strip()
                for field in ("aspect", "observation", "evidence")
            ):
                raise ValueError("UX 항목에는 관찰 대상·내용·근거가 필요")
        if any(x["kind"] == "ux" and x["service"] == event["service"] for x in doc["events"]):
            raise ValueError("UX 기록 덮어쓰기 금지; 정정 note를 추가하세요")
        return
    key = event.get("request_id")
    if not isinstance(key, str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,99}", key):
        raise ValueError("유효한 request_id 필요")
    history = [x for x in doc["events"] if x.get("request_id") == key]
    if kind == "reserve":
        if history:
            raise ValueError("중복 전송 금지: 기존 request_id 확인 필요")
        for field in ("service", "model", "reasoning", "case_id", "ui_evidence", "authorization_scope"):
            if not isinstance(event.get(field), str) or not event[field].strip():
                raise ValueError(field + " 근거 필요")
        if event["service"] not in {"monogpt", "timely", "chatgpt"}:
            raise ValueError("새 서비스는 규격·검증 후 코드에 등록")
        case = next((c for c in doc["cases"] if c["id"] == event["case_id"]), None)
        scope_models = doc.get("report_scope", {}).get("models", [])
        if scope_models:
            model = next((m for m in scope_models if m["id"] == event.get("candidate_id")), None)
            if model is None:
                raise ValueError("고정 실행 계획의 candidate_id 필요")
            if (not model.get("enabled") or event["service"] not in model.get("services", [])
                    or event["case_id"] not in model.get("case_ids", [c["id"] for c in doc["cases"]])):
                raise ValueError("고정 실행 계획 밖의 모델·서비스·질문")
        if case is None or event.get("prompt") not in case["turns"]:
            raise ValueError("고정 프롬프트 불일치")
        actual = hashlib.sha256(event["prompt"].encode()).hexdigest()
        if event.get("prompt_sha256") != actual:
            raise ValueError("프롬프트 해시 불일치")
        if event.get("comparison_tier") not in {"ui_matched", "exploratory"}:
            raise ValueError("UI 일치 또는 탐색적 비교 여부 명시")
        exclusions = event.get("excluded_services", {})
        if not isinstance(exclusions, dict) or any(
            service not in {"monogpt", "timely", "chatgpt"} or service == event["service"]
            or not isinstance(reason, str) or not reason.strip()
            for service, reason in exclusions.items()
        ):
            raise ValueError("제외 서비스와 검증된 사유 필요")
        if event["reasoning"] in {"unknown", "not_exposed"} and event["comparison_tier"] != "exploratory":
            raise ValueError("미공개 추론을 동일 조건으로 처리할 수 없음")
        if not isinstance(event.get("feature_settings"), dict) or not event["feature_settings"]:
            raise ValueError("검색·도구 등 설정 기록 필요")
        for fixture_id in case["fixture_ids"]:
            fixture = event.get("fixtures", {}).get(fixture_id, {})
            if (not re.fullmatch(r"[a-f0-9]{64}", fixture.get("sha256", ""))
                    or fixture.get("reviewed") is not True
                    or event["service"] not in fixture.get("allowed_services", [])):
                raise ValueError("파일 검토·해시·허용 서비스 필요")
        limit = event.get("request_limit")
        if type(limit) is not int or not 1 <= limit <= 40:
            raise ValueError("실행 요청 상한 1~40 필요")
        reserves = [e for e in doc["events"] if e["kind"] == "reserve"]
        if len(reserves) >= min([limit] + [e["request_limit"] for e in reserves]):
            raise ValueError("배치 상한 도달; 기존 상한을 올려 재개하지 마세요")
        if event.get("cost_mode") not in {"bounded", "request_limited_unknown_price"}:
            raise ValueError("비용 제한 방식 필요")
        if event["cost_mode"] == "request_limited_unknown_price" and event.get("unknown_price_acknowledged") is not True:
            raise ValueError("가격 상한 미확정의 한계를 알린 승인 근거 필요")
        if event["cost_mode"] == "bounded":
            raise ValueError("금액 제한 자동 집행 미구현: 엄격 plan과 별도 예산 확인 필요")
        pending = {e["request_id"]: e for e in reserves}
        for e in doc["events"]:
            if e["kind"] == "result":
                pending.pop(e["request_id"], None)
        if any(e["service"] == event["service"] for e in pending.values()):
            raise ValueError("같은 서비스에 미확정 전송이 있음; 먼저 대화와 비용 확인")
        # Conditions cannot drift within a declared matched comparison group.
        for e in reserves:
            if e["case_id"] == event["case_id"] and e["model"] == event["model"]:
                for field in ("prompt_sha256", "reasoning", "fixtures", "feature_settings"):
                    if e.get(field) != event.get(field):
                        raise ValueError("비교 조건 변경: " + field)
    elif kind == "result":
        if not history or history[0]["kind"] != "reserve":
            raise ValueError("전송 예약 없는 결과")
        if any(x["kind"] == "result" for x in history):
            raise ValueError("결과 덮어쓰기 금지; 정정 note를 추가하세요")
        if event.get("status") not in {"success", "unsupported", "automation_error", "service_error", "timeout", "not_sent"}:
            raise ValueError("결과 상태 필요")
        if event["status"] == "success" and not event.get("answer"):
            raise ValueError("성공에는 원문이 필요합니다")
        if 'model_match' in event and type(event['model_match']) is not bool:
            raise ValueError("model_match는 boolean")
        if event.get('model_match') is False and (not event.get('actual_model') or not event.get('limitations')):
            raise ValueError("모델 전환은 actual_model과 limitations 근거 필요")
        for field in ("first_complete_observed_ms", "last_generating_observed_ms"):
            value = event.get(field)
            if value is not None and (type(value) not in (int, float) or not 0 <= value < float("inf")):
                raise ValueError("유효한 관측 시간 필요")
        upper, lower = event.get("first_complete_observed_ms"), event.get("last_generating_observed_ms")
        if upper is not None and lower is not None and upper < lower:
            raise ValueError("시간 구간 역전")
        if event.get("cost_status") not in {"ledger_verified", "balance_observed", "contaminated", "pending", "unavailable"}:
            raise ValueError("비용 관측 상태 필요")
        if event.get("cost_status") in {"contaminated", "pending", "unavailable"} and event.get("cost") is not None:
            raise ValueError("미확정 비용은 null; 내역별 금액은 cost_components에 기록")
    else:
        result = next((x for x in history if x["kind"] == "result"), None)
        if result is None or result["status"] != "success":
            raise ValueError("성공 결과 기록 뒤에만 답변 평가 가능")
        if any(x["kind"] == "assessment" for x in history):
            raise ValueError("평가 덮어쓰기 금지; 정정 note를 추가하세요")
        if not isinstance(event.get("evaluator"), str) or not event["evaluator"].strip():
            raise ValueError("평가자 필요")
        if type(event.get("blind")) is not bool:
            raise ValueError("블라인드 평가 여부 필요")
        reserve = history[0]
        case = next(c for c in doc["cases"] if c["id"] == reserve["case_id"])
        criteria = event.get("criteria")
        if not isinstance(criteria, list) or len(criteria) != len(case["rubric"]):
            raise ValueError("질문별 모든 평가 기준 필요")
        for expected, item in zip(case["rubric"], criteria):
            if not isinstance(item, dict) or item.get("criterion") != expected:
                raise ValueError("평가 기준명·순서 불일치")
            if type(item.get("score")) is not int or not 0 <= item["score"] <= 4:
                raise ValueError("성공 답변 기준별 점수는 0~4 정수")
            for field in ("observation", "judgement", "evidence_ref"):
                if not isinstance(item.get(field), str) or not item[field].strip():
                    raise ValueError("각 기준에 관찰·판단·답변/검사 위치 근거 필요")


def status(root, name):
    doc = read_session(root, name)
    reserved = {e["request_id"] for e in doc["events"] if e["kind"] == "reserve"}
    finished = {e["request_id"] for e in doc["events"] if e["kind"] == "result"}
    return {"reserved": len(reserved), "recorded": len(finished),
            "needs_reconciliation_do_not_resend": sorted(reserved - finished)}
