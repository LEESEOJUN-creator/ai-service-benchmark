import argparse
import json
from pathlib import Path

from .planning import build_plan


def main():
    parser = argparse.ArgumentParser(description="오프라인 비교 계획 점검 (브라우저 실행 없음)")
    parser.add_argument("command", choices=["plan"])
    parser.add_argument("--config", default="config/benchmark.json")
    args = parser.parse_args()
    root = Path(__file__).resolve().parent.parent
    try:
        plan = build_plan(root, args.config)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print(json.dumps({"status": "invalid_configuration", "error": str(exc)}, ensure_ascii=False, indent=2))
        return 2
    print(json.dumps(plan, ensure_ascii=False, indent=2))
    return 0 if plan["status"] == "ready_for_implementation" else 2


if __name__ == "__main__":
    raise SystemExit(main())
