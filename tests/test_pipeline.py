import pytest
from fastapi.testclient import TestClient

import main
from conftest import REQUEST, SOURCE_RESUME, TAILORED_RESUME, FakeEmbedder, fake_llm


# ---------------------------------------------------------------- parsing helpers

def test_parse_json_object_handles_fences_and_prose():
    assert main.parse_json_object('```json\n{"a": 1}\n```') == {"a": 1}
    assert main.parse_json_object('Here you go: {"a": 1} hope that helps') == {"a": 1}
    assert main.parse_json_object("not json") == {}
    assert main.parse_json_object(None) == {}


def test_parse_json_list():
    assert main.parse_json_list('[{"x": 1}]') == [{"x": 1}]
    assert main.parse_json_list("Result: [1, 2] done") == [1, 2]
    assert main.parse_json_list('{"not": "a list"}') == []


# ---------------------------------------------------------------- guardrails

def test_completeness_detects_dropped_entry():
    # Regression: the year regex used to capture only "19"/"20", so nothing was ever flagged.
    final = SOURCE_RESUME.replace("Junior Developer | StartupX | Austin, TX | 2019 - 2020\n", "").replace("| 2019", "")
    result = main.check_completeness(SOURCE_RESUME, final)
    assert any("StartupX" in line for line in result["possibly_missing"])
    assert result["completeness_pct"] < 100


def test_completeness_full_when_nothing_dropped():
    assert main.check_completeness(SOURCE_RESUME, TAILORED_RESUME)["completeness_pct"] == 100


@pytest.mark.parametrize("reply", [
    "",
    None,
    "I’m ready to rewrite your resume, but I need the original content first. Please paste the resume text.",
    "I'm ready to rewrite your resume, but I need the original content first. Please paste the resume text you'd like me to work on. " * 3,
    "Jordan Lee\nEXPERIENCE\n- short",
])
def test_is_usable_resume_rejects_non_resumes(reply):
    assert not main.is_usable_resume(reply, SOURCE_RESUME)


def test_is_usable_resume_accepts_real_resume():
    assert main.is_usable_resume(TAILORED_RESUME, SOURCE_RESUME)


def test_call_llm_without_providers_raises(monkeypatch):
    monkeypatch.setattr(main, "groq_client", None)
    monkeypatch.setattr(main, "client", None)
    with pytest.raises(main.LLMUnavailableError):
        main.call_llm("hello")

# ---------------------------------------------------------------- orchestrator

def test_orchestrator_happy_path(pipeline):
    messages = []
    result = pipeline.orchestrator(dict(REQUEST), "req-1", progress_callback=messages.append)
    wf = result["workflow"]

    assert result["status"] == "success"
    assert "logs" not in result
    assert wf["analyzer"]["candidate_level"] == "Mid-Level"
    assert wf["human_optimizer"]["human_friendly_resume"] == TAILORED_RESUME
    assert wf["recruiter_snapshot"]["snapshot"].startswith("Jordan Lee")
    assert wf["cover_letter"]["cover_letter"].startswith("Dear Hiring Manager")
    assert len(wf["reviewer"]["suggestions"]) == 1  # the no-op suggestion is filtered out
    assert wf["completeness_check"]["completeness_pct"] == 100
    assert wf["ats_optimization"]["missing_keywords"] == ["Kubernetes"]
    assert messages, "progress callback should be called"


def test_orchestrator_reports_before_and_after_ats(pipeline):
    ats = pipeline.orchestrator(dict(REQUEST), "req-2")["workflow"]["ats_optimization"]
    for version in ("before", "after"):
        assert 0 <= ats[version]["ats_score"] <= 100
        assert ats[version]["semantic_score"] is not None
    assert ats["before"]["ats_score"] == ats["ats_score"]


def test_optimizer_conversational_reply_falls_back_to_draft(pipeline, monkeypatch):
    # Regression for the live bug: the optimizer asked for the resume instead of returning one.
    def llm(prompt):
        if "Human sounding" in prompt:
            return "I’m ready to rewrite your resume, but I need the original content first. Please paste the resume text you’d like me to work on."
        return fake_llm(prompt)

    monkeypatch.setattr(main, "call_llm", llm)
    wf = pipeline.orchestrator(dict(REQUEST), "req-3")["workflow"]
    assert wf["human_optimizer"]["human_friendly_resume"] == TAILORED_RESUME
    assert wf["human_optimizer"]["fell_back_to_draft"] is True


def test_optimizer_dropping_entries_falls_back_to_draft(pipeline, monkeypatch):
    shortened = TAILORED_RESUME.replace("Junior Developer | StartupX | Austin, TX | 2019 - 2020\n", "")

    def llm(prompt):
        return shortened if "Human sounding" in prompt else fake_llm(prompt)

    monkeypatch.setattr(main, "call_llm", llm)
    wf = pipeline.orchestrator(dict(REQUEST), "req-4")["workflow"]
    assert "StartupX" in wf["human_optimizer"]["human_friendly_resume"]


def test_writer_retries_once_then_succeeds(pipeline, monkeypatch):
    calls = {"writer": 0}

    def llm(prompt):
        if "Generate a professional ATS-friendly resume" in prompt:
            calls["writer"] += 1
            return "" if calls["writer"] == 1 else TAILORED_RESUME
        return fake_llm(prompt)

    monkeypatch.setattr(main, "call_llm", llm)
    pipeline.orchestrator(dict(REQUEST), "req-5")
    assert calls["writer"] == 2


def test_writer_failing_twice_raises(pipeline, monkeypatch):
    def llm(prompt):
        if "Generate a professional ATS-friendly resume" in prompt:
            return "Please paste the resume text."
        return fake_llm(prompt)

    monkeypatch.setattr(main, "call_llm", llm)
    with pytest.raises(main.ResumeGenerationError):
        pipeline.orchestrator(dict(REQUEST), "req-6")


def test_orchestrator_without_job_description(pipeline):
    request = {**REQUEST, "job_description": None}
    ats = pipeline.orchestrator(request, "req-7")["workflow"]["ats_optimization"]
    assert ats["before"]["semantic_score"] is None
    assert ats["after"]["semantic_score"] is None

# ---------------------------------------------------------------- Qdrant privacy

def test_resume_chunks_are_deleted_after_request(pipeline, monkeypatch):
    qdrant = pytest.importorskip("qdrant_client")
    from qdrant_client import models

    client = qdrant.QdrantClient(":memory:")
    client.create_collection(main.COLLECTION_NAME,
                             vectors_config=models.VectorParams(size=FakeEmbedder.dim, distance=models.Distance.COSINE))
    for name in ("PointStruct", "Filter", "FieldCondition", "MatchValue", "FilterSelector"):
        monkeypatch.setattr(main, name, getattr(models, name), raising=False)
    monkeypatch.setattr(main, "qdrant_client", client)

    result = pipeline.orchestrator(dict(REQUEST), "req-8")
    assert result["rag_matches_used"] > 0
    assert client.count(main.COLLECTION_NAME).count == 0

# ---------------------------------------------------------------- REST API

def test_api_rejects_wrong_key():
    response = TestClient(main.app).post("/generate_resume", json={**REQUEST, "api_key": "wrong"})
    assert response.status_code == 401


def test_api_returns_503_when_no_llm(monkeypatch):
    monkeypatch.setattr(main, "groq_client", None)
    monkeypatch.setattr(main, "client", None)
    response = TestClient(main.app).post("/generate_resume", json={**REQUEST, "api_key": "test-key-123"})
    assert response.status_code == 503


def test_api_success(pipeline):
    response = TestClient(main.app).post("/generate_resume", json={**REQUEST, "api_key": "test-key-123"})
    assert response.status_code == 200
    assert "recruiter_snapshot" in response.json()["workflow"]
