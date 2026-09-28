"""Offline tests for the eval harness itself (the real evals call the AI; these use fakes)."""
import copy
import json

import pytest

import main
from conftest import REQUEST, SOURCE_RESUME, TAILORED_RESUME
from evals import runner
from evals.checks import run_checks
from evals.judge import RUBRIC


def fake_judge(original, job_description, tailored):
    return {"scores": {name: 4 for name in RUBRIC}, "overall": 4.0, "unsupported_claims": [], "notes": ""}


def make_result(final=TAILORED_RESUME, lost=(), after_items=None, before_score=70, after_score=80):
    items = after_items if after_items is not None else [
        {"id": "r1", "text": "3+ years", "category": "experience_years", "status": "met", "keywords": []}]
    return {"workflow": {
        "human_optimizer": {"human_friendly_resume": final},
        "ats_optimization": {"lost_keywords": list(lost), "before": {"ats_score": 60}, "after": {"ats_score": 70}},
        "requirement_match": {"before": {"score": before_score, "items": items},
                              "after": {"score": after_score, "items": items}},
    }}


CASE = {"id": "t", "request": {**REQUEST}, "expect": {}}


def names_failed(checks):
    return {c["name"] for c in checks if not c["passed"]}


# ---------------------------------------------------------------- golden cases

def test_golden_cases_are_well_formed():
    cases = runner.load_cases()
    assert len(cases) >= 6 and len({c["id"] for c in cases}) == len(cases)
    for case in cases:
        request = case["request"]
        for field in ("full_name", "current_role", "skills", "experience_years", "resume_text", "job_description"):
            assert field in request, (case["id"], field)
        for expected in case["expect"].get("requirements", []):
            assert set(expected["status"]) <= set(main.STATUS_CREDIT)
        assert case["expect"].get("years_status") in (None, *main.STATUS_CREDIT)


def test_unknown_case_id_is_rejected():
    with pytest.raises(ValueError):
        runner.load_cases(["nope"])


def test_prompt_versions_render_and_differ():
    values = dict(job_description="JD", keep="Python", gaps="Go")
    v1 = main.render_prompt("tailoring", "v1", **values)
    v2 = main.render_prompt("tailoring", "v2", **values)
    assert "Python" in v1 and "Requirement coverage" in v2 and "Requirement coverage" not in v1
    assert "$" not in main.render_prompt("tailoring", "v1", job_description="Pay: $120k", keep="", gaps="").replace("$120k", "")

# ---------------------------------------------------------------- checks

def test_clean_result_passes_all_checks():
    assert names_failed(run_checks(CASE, make_result())) == set()


def test_invented_number_is_caught():
    fake = TAILORED_RESUME.replace("reducing infrastructure costs by 20%", "reducing infrastructure costs by 45%")
    checks = run_checks(CASE, make_result(final=fake))
    assert "no_invented_numbers" in names_failed(checks)
    assert "45" in next(c["detail"] for c in checks if c["name"] == "no_invented_numbers")


def test_dropped_job_lost_keyword_and_markdown_are_caught():
    dropped = TAILORED_RESUME.replace("Junior Developer | StartupX | Austin, TX | 2019 - 2020\n", "")
    assert "all_entries_kept" in names_failed(run_checks(CASE, make_result(final=dropped)))
    assert "job_keywords_kept" in names_failed(run_checks(CASE, make_result(lost=["Docker"])))
    assert "resume_format" in names_failed(run_checks(CASE, make_result(final="**" + TAILORED_RESUME)))


def test_case_expectations():
    case = copy.deepcopy(CASE)
    case["expect"] = {"years_status": "partial", "must_not_contain": ["Docker"],
                      "requirements": [{"term": "Kubernetes", "status": ["not_met"]}],
                      "requirement_score_after": {"max": 50}}
    items = [{"id": "r1", "text": "6+ years", "category": "experience_years", "status": "met", "keywords": []},
             {"id": "r2", "text": "Kubernetes", "category": "skill", "status": "met", "keywords": ["Kubernetes"]}]
    checks = run_checks(case, make_result(after_items=items))
    assert {"years_verdict", "not_invented:Docker", "requirement:Kubernetes", "requirement_score_in_range"} <= names_failed(checks)
    assert next(c for c in checks if c["name"] == "requirement_score_in_range")["hard"] is False

# ---------------------------------------------------------------- gate

def report(overall=4.0, truth=4.0, req=80, ats=70, failed_check=False):
    checks = [{"name": "x", "passed": not failed_check, "detail": "bad", "hard": True}]
    return {"summary": {"judge_overall": overall, "judge_truthfulness": truth, "requirement_after": req,
                        "ats_after": ats, "judge_unparsed": 0},
            "cases": [{"id": "c1", "checks": checks}]}


def test_gate_passes_within_margins():
    assert runner.gate(report(), report(overall=3.8, req=76))[0]


@pytest.mark.parametrize("candidate, reason", [
    (report(failed_check=True), "check 'x' failed"),
    (report(overall=3.5), "judge_overall dropped"),
    (report(truth=3.6), "judge_truthfulness dropped"),
    (report(req=70), "requirement_after dropped"),
])
def test_gate_fails_on_regression(candidate, reason):
    passed, problems = runner.gate(report(), candidate)
    assert not passed and any(reason in p for p in problems)

# ---------------------------------------------------------------- end to end (fake AI)

def test_run_suite_end_to_end_with_fakes(pipeline, tmp_path, monkeypatch):
    case = {"id": "fake", "request": dict(REQUEST), "expect": {
        "years_status": "met", "requirements": [{"term": "Kubernetes", "status": ["not_met"]}]}}
    (tmp_path / "fake.json").write_text(json.dumps(case))
    monkeypatch.setattr(runner, "CASES_DIR", tmp_path)
    result = runner.run_suite("v1", progress=lambda msg: None, judge=fake_judge)
    summary = result["summary"]
    assert summary["hard_checks_passed"] == summary["hard_checks_total"]
    assert summary["judge_overall"] == 4.0 and result["prompt_version"] == "v1"
    assert runner.gate(result, result)[0]


def test_rate_limit_aborts_instead_of_failing_quality(pipeline, monkeypatch):
    def busy(prompt, **kwargs):
        raise main.LLMBusyError("limit", daily=True)

    monkeypatch.setattr(main, "call_llm", busy)
    with pytest.raises(runner.EvalAborted, match="daily limit"):
        runner.run_case({"id": "x", "request": dict(REQUEST), "expect": {}}, "v1", judge=fake_judge)


def test_cli_requires_api_key(monkeypatch, capsys):
    from evals.__main__ import main_cli
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    assert main_cli(["run"]) == 2
    assert "GROQ_API_KEY" in capsys.readouterr().out


def test_frozen_requirements_round_trip(pipeline, tmp_path):
    cases = [{"id": "fake", "request": dict(REQUEST), "expect": {}}]
    path = tmp_path / "requirements.json"
    assert runner.load_frozen_requirements(cases, path=path) == ["fake"]      # nothing frozen yet
    main.extract_job_requirements(REQUEST["job_description"])                  # the run extracts...
    runner.save_frozen_requirements(cases, path=path)                          # ...and freezes
    main._JOB_REQUIREMENTS_CACHE.clear()
    assert runner.load_frozen_requirements(cases, path=path) == []            # now seeded from the file
    assert main._JOB_REQUIREMENTS_CACHE[main.job_cache_key(REQUEST["job_description"])]
    assert runner.load_frozen_requirements(cases, refresh=True, path=path) == ["fake"]


def test_per_minute_rate_limit_waits_and_retries(pipeline, monkeypatch):
    monkeypatch.setattr(runner, "RATE_LIMIT_WAIT_SECONDS", 0)
    attempts = []

    def flaky_judge(*args):
        attempts.append(1)
        if len(attempts) < 3:
            raise main.LLMBusyError("per-minute limit")
        return fake_judge(*args)

    result = runner.run_case({"id": "x", "request": dict(REQUEST), "expect": {}}, "v1",
                             judge=flaky_judge, progress=lambda m: None)
    assert len(attempts) == 3 and result["judge"]["overall"] == 4.0
