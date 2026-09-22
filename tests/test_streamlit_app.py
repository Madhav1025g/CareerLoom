"""End-to-end UI tests: drive the real Streamlit page with the fake LLM."""
import pytest
from streamlit.testing.v1 import AppTest

import main
from conftest import ROOT, TAILORED_RESUME, FakeEmbedder, fake_llm

APP = str(ROOT / "streamlit_app.py")


@pytest.fixture
def app(monkeypatch):
    monkeypatch.chdir(ROOT)
    monkeypatch.setattr(main, "call_llm", fake_llm)
    monkeypatch.setattr(main, "embedding_model", FakeEmbedder())
    return AppTest.from_file(APP, default_timeout=60).run()


def button(at, label):
    return next(b for b in at.button if b.label == label)


def generate(at):
    button(at, "Load example").click().run()
    button(at, "Generate my application").click().run()
    return at


def test_page_loads_without_errors(app):
    assert not app.exception
    assert any(b.label == "Generate my application" for b in app.button)


def test_generate_shows_all_results(app):
    at = generate(app)
    assert not at.exception, at.exception
    assert [t.label for t in at.tabs] == [
        "Tailored resume", "Recruiter snapshot", "Cover letter", "ATS analysis", "Review suggestions", "First draft",
    ]
    labels = [m.label for m in at.metric]
    assert labels[:4] == ["ATS match", "Experience preserved", "Review suggestions", "Candidate level"]
    assert at.session_state.docs["resume"] == TAILORED_RESUME
    assert at.session_state.generation_count == 1


def test_apply_suggestion_updates_resume(app):
    at = generate(app)
    button(at, "Apply").click().run()
    assert "internal analytics dashboards" in at.session_state.docs["resume"]
    assert not at.exception


@pytest.mark.parametrize("template", ["Modern", "Classic", "Compact"])
def test_switching_template(app, template):
    at = generate(app)
    at.segmented_control(key="template").set_value(template).run()
    assert not at.exception


def test_edit_mode_saves_changes(app):
    at = generate(app)
    at.segmented_control(key="mode_resume").set_value("Edit").run()
    editor = next(t for t in at.text_area if t.key and t.key.startswith("editor_resume_"))
    editor.set_value(TAILORED_RESUME + "\nAWARDS\n- Employee of the Year").run()
    assert "Employee of the Year" in at.session_state.docs["resume"]
    assert not at.exception


def test_llm_outage_shows_error_and_does_not_count(app, monkeypatch):
    def down(prompt):
        raise main.LLMUnavailableError("down")

    monkeypatch.setattr(main, "call_llm", down)
    at = generate(app)
    assert any("temporarily unavailable" in e.value for e in at.error)
    assert at.session_state.generation_count == 0


def test_broken_resume_output_shows_error(app, monkeypatch):
    def broken(prompt):
        if "Generate a professional ATS-friendly resume" in prompt:
            return "Please paste the resume text."
        return fake_llm(prompt)

    monkeypatch.setattr(main, "call_llm", broken)
    at = generate(app)
    assert any("couldn't generate a complete resume" in e.value for e in at.error)


def test_resume_tab_shows_score_bar_chart(app):
    at = generate(app)
    charts = at.get("vega_lite_chart")
    assert len(charts) >= 2  # bar chart under downloads + dumbbell chart in the ATS tab
    assert any("ATS score" in m.value for m in at.markdown)
