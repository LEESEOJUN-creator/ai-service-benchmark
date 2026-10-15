import argparse
import json
from pathlib import Path

from .planning import build_plan
from .session import initialize, append_event, status
from .reporting import report


def main():
    parser = argparse.ArgumentParser(description="비교 계획·비공개 실행 기록·보고서 (실제 UI는 연결된 에이전트가 조작)")
    parser.add_argument("command", choices=["plan", "init", "record", "status", "report"])
    parser.add_argument("--config", default="config/benchmark.json")
    parser.add_argument("--run", default="comparison")
    parser.add_argument("--cases", default="cases/core.json")
    parser.add_argument("--event", help="Git 제외 로컬 이벤트 JSON")
    parser.add_argument("--report-date", help="PDF·XLSX 파일명 날짜 YYYY-MM-DD (기본: 실행일)")
    parser.add_argument("--rates", help="로컬 서비스별 1크레딧당 원화 환산율 JSON (예: local/credit-rates.json)")
    parser.add_argument("--output-dir", help="보고서 저장 폴더 (기본: ~/AI-Benchmark-Reports/<run-id>)")
    args = parser.parse_args()
    root = Path(__file__).resolve().parent.parent
    try:
        if args.command != "plan":
            if args.command == "init":
                result = initialize(root, args.run, args.cases)
            elif args.command == "record":
                if not args.event:
                    raise ValueError("--event 필요")
                result = append_event(root, args.run, json.loads(Path(args.event).read_text(encoding="utf-8")))
            elif args.command == "status":
                result = status(root, args.run)
            else:
                rates = json.loads(Path(args.rates).read_text(encoding="utf-8")) if args.rates else None
                result = report(root, args.run, report_date=args.report_date, credit_rates=rates,
                                output_dir=args.output_dir)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0
        plan = build_plan(root, args.config)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print(json.dumps({"status": "invalid_configuration", "error": str(exc)}, ensure_ascii=False, indent=2))
        return 2
    print(json.dumps(plan, ensure_ascii=False, indent=2))
    return 0 if plan["status"] == "ready_for_implementation" else 2


if __name__ == "__main__":
    raise SystemExit(main())
