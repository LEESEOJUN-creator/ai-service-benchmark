"""Durable external UI clock, independent of browser/REPL implementation.

The agent observes the UI. This module never clicks, polls or infers completion.
Clock samples are created by the journal writer, not supplied by the agent.
"""
import time
from datetime import datetime, timezone


def clock_sample():
    # Python <3.10 on macOS implements monotonic() with a per-process origin.
    # CLOCK_MONOTONIC is host-wide and therefore survives separate CLI calls.
    monotonic = (time.clock_gettime_ns(time.CLOCK_MONOTONIC)
                 if hasattr(time, 'CLOCK_MONOTONIC') and hasattr(time, 'clock_gettime_ns')
                 else time.monotonic_ns())
    return {"epoch_ms": time.time_ns() / 1_000_000,
            "monotonic_ms": monotonic / 1_000_000}


def stamp_event(event):
    event = dict(event)
    event["clock"] = clock_sample()
    return event


def validate_timing(history, event):
    phase = event.get("phase")
    if phase not in {"start", "generating", "complete"}:
        raise ValueError("timer phase: start/generating/complete")
    if not isinstance(event.get("evidence"), str) or not event["evidence"].strip():
        raise ValueError("현재 요청의 UI 확인 근거 필요")
    if not history or history[0]["kind"] != "reserve":
        raise ValueError("타이머 전에 reserve 필요")
    if any(e["kind"] == "result" for e in history):
        raise ValueError("결과 기록 후 과거 시각을 새로 측정할 수 없음; 재전송 금지")
    samples = [e for e in history if e["kind"] == "timing"]
    if phase == "start":
        if samples:
            raise ValueError("시작 시계 재설정 금지; 저장된 시계로 관측만 재개")
    elif not samples or samples[0]["phase"] != "start":
        raise ValueError("전송 전 저장된 시작 시계 없음; 추정/재전송 금지")
    if any(e["phase"] == "complete" for e in samples):
        raise ValueError("최초 완료 시각 보존; 재관측으로 덮어쓰지 않음")


def timing_fields(history):
    samples = [e for e in history if e["kind"] == "timing"]
    if not samples:
        return {}  # Legacy or browser/observe.mjs records keep their own evidence.
    complete = next((e for e in samples if e["phase"] == "complete"), None)
    missing = {"first_complete_observed_ms": None, "last_generating_observed_ms": None,
               "timing_method": "durable_external_ui_clock",
               "timing_unavailable_reason": "시계는 저장됐으나 완료 관측이 없음; 재전송 금지"}
    if complete is None:
        return missing
    start = samples[0]["clock"]
    elapsed = []
    for sample in samples[1:]:
        clock = sample["clock"]
        mono = clock["monotonic_ms"] - start["monotonic_ms"]
        wall = clock["epoch_ms"] - start["epoch_ms"]
        # Monotonic clock survives Python process changes on the same host.
        # Reboot, host change, sleep/platform anomalies or wall clock adjustment
        # are not silently turned into plausible response times.
        if mono < 0 or wall < 0 or abs(mono - wall) > 2000:
            return dict(missing, timing_unavailable_reason="시계 불일치/재시작 감지; 원기록 검토, 재전송 금지")
        elapsed.append((sample, mono))
    upper = next(ms for e, ms in elapsed if e["phase"] == "complete")
    iso = lambda ms: datetime.fromtimestamp(ms / 1000, timezone.utc).isoformat()
    return {"first_complete_observed_ms": upper,
            # Tool return time is not the snapshot acquisition time. Do not turn
            # a post-snapshot generating marker into a false lower bound.
            "last_generating_observed_ms": None,
            "sent_at": iso(start["epoch_ms"]),
            "completed_at": iso(complete["clock"]["epoch_ms"]),
            "timing_method": "durable_external_ui_clock_including_tool_overhead",
            "timing_evidence": complete["evidence"], "timing_unavailable_reason": None}


def merge_timing(doc, event):
    if event.get("kind") != "result":
        return event
    history = [e for e in doc["events"] if e.get("request_id") == event.get("request_id")]
    fields = timing_fields(history)
    for key in ("first_complete_observed_ms", "last_generating_observed_ms"):
        if fields and event.get(key) is not None and event[key] != fields.get(key):
            raise ValueError("저장된 시계와 수동 시간값 충돌; 수동 필드를 제거하고 원기록 확인")
    return dict(event, **fields)  # Null in a custom recorder cannot erase the clock.
