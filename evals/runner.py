"""Run golden cases through the pipeline, grade them, summarize, compare, and gate."""
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import main
from evals.checks import run_checks
from evals.judge import JUDGE_MODEL, RUBRIC, judge_resume

CASES_DIR = Path(__file__).resolve().parent / "cases"
BASELINE_PATH = Path(__file__).resolve().parent / "baseline.json"

# Quality gate: the candidate fails if any hard check fails, or if it drops more than these margins below the
# baseline (margins absorb normal run-to-run variation of LLM output).
GATE_MARGINS = {
    "judge_overall": 0.3,        # 1-5 scale
    "judge_truthfulness": 0.3,   # 1-5 scale — honesty gets its own bar
    "requirement_after": 5,      # 0-100
    "ats_after": 5,              # 0-100
}


class EvalAborted(RuntimeError):
    """The run couldn't finish for infrastructure reasons (e.g. API rate limit) — not a quality failure."""


def load_cases(case_ids=None) -> list[dict]:
    cases = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(CASES_DIR.glob("*.json"))]
    if case_ids:
        wanted = set(case_ids)
        unknown = wanted - {c["id"] for c in cases}
        if unknown:
            raise ValueError(f"Unknown case id(s): {', '.join(sorted(unknown))}")
        cases = [c for c in cases if c["id"] in wanted]
    return cases


def run_case(case: dict, prompt_version: str, eval_cache: dict | None = None, judge=judge_resume) -> dict:
    request = {**case["request"], "resume_file": None}
    started = time.time()
    try:
        result = main.orchestrator(request, f"eval-{case['id']}-{prompt_version}", prompt_version=prompt_version,
                                   extras=False, eval_cache=eval_cache)
    except main.LLMBusyError as exc:
        raise EvalAborted(f"AI rate limit reached during case '{case['id']}'"
                          f"{' (daily limit)' if exc.daily else ''}. Try again later.") from exc
    except main.LLMUnavailableError as exc:
        raise EvalAborted(f"AI service unavailable during case '{case['id']}': {exc}") from exc
    except main.ResumeGenerationError as exc:
        return {"id": case["id"], "error": str(exc), "checks": [
            {"name": "pipeline_completed", "passed": False, "detail": str(exc), "hard": True}],
            "judge": {"scores": None, "overall": None}, "scores": {}, "seconds": round(time.time() - started, 1)}

    workflow = result["workflow"]
    final = workflow["human_optimizer"]["human_friendly_resume"]
    requirement_match = workflow.get("requirement_match") or {}
    ats = workflow["ats_optimization"]
    try:
        judgment = judge(case["request"]["resume_text"], case["request"].get("job_description"), final)
    except main.LLMBusyError as exc:
        raise EvalAborted(f"Judge model rate limit reached during case '{case['id']}'. Try again later.") from exc

    return {
        "id": case["id"],
        "seconds": round(time.time() - started, 1),
        "checks": run_checks(case, result),
        "judge": judgment,
        "scores": {
            "requirement_before": (requirement_match.get("before") or {}).get("score"),
            "requirement_after": (requirement_match.get("after") or {}).get("score"),
            "ats_before": ats["before"]["ats_score"],
            "ats_after": ats["after"]["ats_score"],
        },
        "used_draft": bool(workflow["human_optimizer"].get("fell_back_to_draft")),
        "final_resume": final,
    }


def _mean(values):
    values = [v for v in values if v is not None]
    return round(sum(values) / len(values), 2) if values else None


def summarize(case_results: list[dict]) -> dict:
    all_checks = [c for r in case_results for c in r["checks"]]
    hard = [c for c in all_checks if c["hard"]]
    judged = [r["judge"] for r in case_results if r["judge"].get("scores")]
    return {
        "cases": len(case_results),
        "hard_checks_passed": sum(c["passed"] for c in hard),
        "hard_checks_total": len(hard),
        "soft_checks_passed": sum(c["passed"] for c in all_checks if not c["hard"]),
        "soft_checks_total": sum(not c["hard"] for c in all_checks),
        "judge_overall": _mean(j["overall"] for j in judged),
        **{f"judge_{name}": _mean(j["scores"][name] for j in judged) for name in RUBRIC},
        "judge_unparsed": len(case_results) - len(judged),
        **{key: _mean(r["scores"].get(key) for r in case_results)
           for key in ("requirement_before", "requirement_after", "ats_before", "ats_after")},
    }


def run_suite(prompt_version: str, case_ids=None, eval_cache=None, progress=print, judge=judge_resume) -> dict:
    cases = load_cases(case_ids)
    eval_cache = {} if eval_cache is None else eval_cache
    results = []
    for i, case in enumerate(cases, start=1):
        progress(f"[{prompt_version}] {i}/{len(cases)} {case['id']} ...")
        results.append(run_case(case, prompt_version, eval_cache, judge=judge))
    return {
        "prompt_version": prompt_version,
        "model": main.GROQ_MODEL,
        "judge_model": JUDGE_MODEL,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "summary": summarize(results),
        "cases": results,
    }


def gate(baseline: dict, candidate: dict, margins: dict = GATE_MARGINS) -> tuple[bool, list[str]]:
    """Pass/fail the candidate: all hard checks must pass, and no metric may drop more than its margin."""
    problems = []
    for case in candidate["cases"]:
        for c in case["checks"]:
            if c["hard"] and not c["passed"]:
                problems.append(f"{case['id']}: check '{c['name']}' failed — {c['detail']}")
    if candidate["summary"].get("judge_unparsed"):
        problems.append(f"{candidate['summary']['judge_unparsed']} case(s) could not be judged")
    base, cand = baseline["summary"], candidate["summary"]
    for metric, margin in margins.items():
        if base.get(metric) is None or cand.get(metric) is None:
            continue
        if cand[metric] < base[metric] - margin:
            problems.append(f"{metric} dropped from {base[metric]} to {cand[metric]} (allowed drop: {margin})")
    return not problems, problems


def save(report: dict, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")


def load(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))
