"""
Command line for the CareerLoom eval harness.

  python -m evals run                      # run the golden set with the live prompt version
  python -m evals run --save-baseline      # ...and store it as the baseline the gate compares against
  python -m evals compare --baseline v1 --candidate v2
  python -m evals gate                     # run + compare with evals/baseline.json; exit 1 if quality dropped

Needs GROQ_API_KEY (in .env locally, or a GitHub Actions secret in CI).
"""
import argparse
import os
import sys
from pathlib import Path

import evals  # noqa: F401  (sets eval-safe environment before main is imported)
import main
from evals import runner

RESULTS_DIR = Path(__file__).resolve().parent / "results"


def _fmt(value, width=6):
    return f"{value:>{width}}" if value is not None else f"{'—':>{width}}"


def print_report(report: dict):
    s = report["summary"]
    print(f"\nPrompt version {report['prompt_version']}  ·  writer {report['model']}  ·  judge {report['judge_model']}")
    print(f"{'case':<18}{'checks':>9}{'judge':>7}{'req before→after':>19}{'ATS before→after':>19}")
    for case in report["cases"]:
        hard = [c for c in case["checks"] if c["hard"]]
        sc = case.get("scores", {})
        print(f"{case['id']:<18}{sum(c['passed'] for c in hard):>5}/{len(hard):<3}{_fmt(case['judge'].get('overall'))}"
              f"{_fmt(sc.get('requirement_before'), 10)} → {_fmt(sc.get('requirement_after'), 3)}"
              f"{_fmt(sc.get('ats_before'), 13)} → {_fmt(sc.get('ats_after'), 3)}")
        for c in case["checks"]:
            if not c["passed"]:
                print(f"{'':<4}{'FAIL' if c['hard'] else 'warn'} {c['name']}: {c['detail']}")
        for claim in case["judge"].get("unsupported_claims", [])[:3]:
            print(f"{'':<4}judge flagged: {claim}")
    print(f"\nHard checks {s['hard_checks_passed']}/{s['hard_checks_total']}  ·  soft checks "
          f"{s['soft_checks_passed']}/{s['soft_checks_total']}  ·  judge overall {s['judge_overall']}")
    print("Judge by dimension: " + ", ".join(f"{k[6:]} {s[k]}" for k in s if k.startswith("judge_")
                                           and k not in ("judge_overall", "judge_unparsed")))
    print(f"Mean requirement match {s['requirement_before']} → {s['requirement_after']}  ·  "
          f"mean ATS match {s['ats_before']} → {s['ats_after']}")


def print_comparison(base: dict, cand: dict):
    print(f"\n{'metric':<24}{base['prompt_version']:>10}{cand['prompt_version']:>10}{'change':>10}")
    for key, value in base["summary"].items():
        other = cand["summary"].get(key)
        if isinstance(value, (int, float)) and isinstance(other, (int, float)) and key != "cases":
            print(f"{key:<24}{value:>10}{other:>10}{round(other - value, 2):>+10}")


def main_cli(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="python -m evals", description="CareerLoom eval harness")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("run", "gate"):
        p = sub.add_parser(name)
        p.add_argument("--prompts", default=main.PROMPT_VERSION, help="prompt version folder (default: live version)")
        p.add_argument("--cases", help="comma-separated case ids (default: all)")
    sub.choices["run"].add_argument("--save-baseline", action="store_true", help="store the result as the baseline")
    sub.choices["gate"].add_argument("--baseline", default=str(runner.BASELINE_PATH))
    compare = sub.add_parser("compare")
    compare.add_argument("--baseline", required=True, help="baseline prompt version, e.g. v1")
    compare.add_argument("--candidate", required=True, help="candidate prompt version, e.g. v2")
    compare.add_argument("--cases", help="comma-separated case ids (default: all)")
    args = parser.parse_args(argv)

    if not os.getenv("GROQ_API_KEY"):
        print("GROQ_API_KEY is not set. Add it to the .env file in the project folder (see evals/README.md).")
        return 2
    case_ids = args.cases.split(",") if args.cases else None

    try:
        if args.command == "compare":
            cache = {}  # the original resume's verdicts are identical for both versions — judge them once
            base = runner.run_suite(args.baseline, case_ids, eval_cache=cache)
            cand = runner.run_suite(args.candidate, case_ids, eval_cache=cache)
            for report in (base, cand):
                runner.save(report, RESULTS_DIR / f"{report['prompt_version']}.json")
                print_report(report)
            print_comparison(base, cand)
            passed, problems = runner.gate(base, cand)
            print(f"\n{args.candidate} vs {args.baseline}: {'PASS' if passed else 'FAIL'}")
            for problem in problems:
                print(f"  - {problem}")
            return 0

        report = runner.run_suite(args.prompts, case_ids)
        runner.save(report, RESULTS_DIR / f"{args.prompts}.json")
        print_report(report)

        if args.command == "run":
            if args.save_baseline:
                runner.save(report, runner.BASELINE_PATH)
                print(f"\nSaved as the baseline: {runner.BASELINE_PATH}")
            return 0

        baseline_path = Path(args.baseline)
        if not baseline_path.exists():
            print(f"\nNo baseline at {baseline_path}. Create one with: python -m evals run --save-baseline")
            return 2
        baseline = runner.load(baseline_path)
        print_comparison(baseline, report)
        passed, problems = runner.gate(baseline, report)
        print(f"\nQuality gate: {'PASS' if passed else 'FAIL'}")
        for problem in problems:
            print(f"  - {problem}")
        return 0 if passed else 1
    except runner.EvalAborted as exc:
        print(f"\nEval aborted (not a quality failure): {exc}")
        return 2


if __name__ == "__main__":
    sys.exit(main_cli())
