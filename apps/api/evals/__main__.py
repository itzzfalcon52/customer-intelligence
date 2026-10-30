import argparse
import sys

from evals.runner import run


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="python -m evals",
        description="Evaluate the retention agent. Replays recorded cassettes unless --live.",
    )
    parser.add_argument("--live", action="store_true", help="call the configured provider")
    parser.add_argument("--record", action="store_true", help="with --live, save cassettes")
    parser.add_argument("--judge", action="store_true", help="with --live, add an LLM judge")
    parser.add_argument("--scenario", action="append", help="run only this scenario")
    parser.add_argument(
        "--repeat", type=int, default=1, help="with --live, sample each scenario N times"
    )
    args = parser.parse_args()
    if (args.record or args.judge or args.repeat > 1) and not args.live:
        parser.error("--record, --judge and --repeat require --live")
    report, path = run(args.live, args.record, args.judge, args.scenario, max(1, args.repeat))
    print(f"\n{'scenario':<22} {'result':<7} {'grounding':>9} {'calls':>5} {'tokens':>7}  notes")
    for item in report["scenarios"]:
        grades = {grade["name"]: grade for grade in item["grades"]}
        grounding = grades.get("numeric_grounding", {}).get("score")
        metrics = item.get("metrics", {})
        tokens = (metrics.get("input_tokens") or 0) + (metrics.get("output_tokens") or 0)
        failed = [name for name, grade in grades.items() if not grade["passed"]]
        notes = item.get("error") or ", ".join(failed)
        ungrounded = grades.get("numeric_grounding", {}).get("details", {}).get("ungrounded")
        if ungrounded:
            notes += f" ungrounded={ungrounded}"
        print(
            f"{item['name']:<22} {'pass' if item['passed'] else 'FAIL':<7} "
            f"{'-' if grounding is None else f'{grounding:.2f}':>9} "
            f"{metrics.get('model_calls') or '-':>5} {tokens or '-':>7}  {notes}"
        )
    if any(item["runs"] > 1 for item in report["by_scenario"].values()):
        print("\npass rate by scenario:")
        for name, item in report["by_scenario"].items():
            print(f"  {name:<22} {item['passed']}/{item['runs']}")
    summary = report["summary"]
    print(
        f"\n{summary['passed']}/{summary['total']} passed · mode={report['mode']} · "
        f"mean grounding={summary['mean_numeric_grounding']} · report: {path}"
    )
    return 0 if summary["passed"] == summary["total"] else 1


if __name__ == "__main__":
    sys.exit(main())
