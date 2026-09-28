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
# Each golden job's extracted requirements, frozen so every run (local, CI, baseline) grades against identical
# lists. Otherwise small differences in extraction between runs would look like prompt regressions.
REQUIREMENTS_PATH = Path(__file__).resolve().parent / "requirements.json"

# Quality gate: the candidate fails if any hard check fails, or if it drops more than these margins below the
# baseline (margins absorb normal run-to-run variation of LLM output).
# Calibrated from repeated runs of the SAME prompts: with 6 cases x 2 samples, averages still move by up to
# ~0.4 (judge overall), ~0.6 (truthfulness), and ~5 (requirement match) from randomness alone. Tighter margins
# made the gate fail on noise. Fabrication itself is caught by the deterministic hard checks, not these margins.
GATE_MARGINS = {
    "judge_overall": 0.5,        # 1-5 scale
    "judge_truthfulness": 0.75,  # 1-5 scale — honesty gets its own bar
    "requirement_after": 8,      # 0-100
    "ats_after": 5,              # 0-100 (deterministic given the resume; varies only with the writer's output)
}
DEFAULT_REPEATS = 2  # samples per case: LLM output varies run to run, so one sample per case is too noisy


class EvalAborted(RuntimeError):
    """The run couldn't finish for infrastructure reasons (e.g. API rate limit) — not a quality failure."""


# Groq's free tier allows ~8,000 tokens per minute per model. When a per-minute limit is hit, wait for the window
# to reset and retry; only a daily limit aborts the run.
RATE_LIMIT_WAIT_SECONDS = 65
RATE_LIMIT_RETRIES = 3


def _with_rate_limit_retries(fn, label, progress=print):
    for attempt in range(RATE_LIMIT_RETRIES + 1):
        try:
            return fn()
        except main.LLMBusyError as exc:
            if exc.daily or attempt == RATE_LIMIT_RETRIES:
                raise
            progress(f"    rate limit hit during {label}; waiting {RATE_LIMIT_WAIT_SECONDS}s ...")
            time.sleep(RATE_LIMIT_WAIT_SECONDS)


def load_cases(case_ids=None) -> list[dict]:
    cases = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(CASES_DIR.glob("*.json"))]
    if case_ids:
        wanted = set(case_ids)
        unknown = wanted - {c["id"] for c in cases}
        if unknown:
            raise ValueError(f"Unknown case id(s): {', '.join(sorted(unknown))}")
        cases = [c for c in cases if c["id"] in wanted]
    return cases


def run_case(case: dict, prompt_version: str, eval_cache: dict | None = None, judge=judge_resume,
             progress=print) -> dict:
    request = {**case["request"], "resume_file": None}
    started = time.time()
    try:
        result = _with_rate_limit_retries(
            lambda: main.orchestrator(request, f"eval-{case['id']}-{prompt_version}", prompt_version=prompt_version,
                                      extras=False, eval_cache=eval_cache),
            f"case '{case['id']}'", progress)
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
        judgment = _with_rate_limit_retries(
            lambda: judge(case["request"]["resume_text"], case["request"].get("job_description"), final),
            f"judging '{case['id']}'", progress)
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


def load_frozen_requirements(cases, refresh=False, path=None) -> list[str]:
    """Seed main's requirement cache from the frozen file. Returns the case ids that still need extraction."""
    path = path or REQUIREMENTS_PATH
    frozen = {} if refresh or not path.exists() else json.loads(path.read_text(encoding="utf-8"))
    missing = []
    for case in cases:
        requirements = frozen.get(case["id"])
        if requirements:
            main._JOB_REQUIREMENTS_CACHE[main.job_cache_key(case["request"]["job_description"])] = requirements
        else:
            missing.append(case["id"])
    return missing


def save_frozen_requirements(cases, path=None):
    """Store what was extracted for each case (only after a run, so the lists match the saved results)."""
    path = path or REQUIREMENTS_PATH
    frozen = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    for case in cases:
        key = main.job_cache_key(case["request"]["job_description"])
        if main._JOB_REQUIREMENTS_CACHE.get(key):
            frozen[case["id"]] = main._JOB_REQUIREMENTS_CACHE[key]
    path.write_text(json.dumps(frozen, indent=2), encoding="utf-8")


def run_suite(prompt_version: str, case_ids=None, eval_cache=None, progress=print, judge=judge_resume,
              refresh_requirements=False, repeats: int = 1) -> dict:
    cases = load_cases(case_ids)
    missing = load_frozen_requirements(cases, refresh=refresh_requirements)
    if missing:
        progress(f"Extracting requirements for: {', '.join(missing)} (will be frozen in {REQUIREMENTS_PATH.name})")
    eval_cache = {} if eval_cache is None else eval_cache
    results = []
    for sample in range(1, repeats + 1):
        for i, case in enumerate(cases, start=1):
            tag = f" (sample {sample}/{repeats})" if repeats > 1 else ""
            progress(f"[{prompt_version}] {i}/{len(cases)} {case['id']}{tag} ...")
            result = run_case(case, prompt_version, eval_cache, judge=judge, progress=progress)
            result["sample"] = sample
            results.append(result)
    if missing:
        save_frozen_requirements([c for c in cases if c["id"] in missing])
    return {
        "prompt_version": prompt_version,
        "model": main.GROQ_MODEL,
        "judge_model": JUDGE_MODEL,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "repeats": repeats,
        "summary": summarize(results),
        "cases": results,
    }


def merge_reports(reports: list[dict]) -> dict:
    """Combine runs of the same prompt version into one report (more samples = a steadier baseline)."""
    versions = {r["prompt_version"] for r in reports}
    if len(versions) != 1:
        raise ValueError(f"Can only merge runs of one prompt version, got {sorted(versions)}")
    cases = []
    for sample, report in enumerate(reports, start=1):
        cases += [{**case, "sample": sample} for case in report["cases"]]
    return {**reports[-1], "repeats": len(reports), "summary": summarize(cases), "cases": cases}


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
