"""End-to-end UI tests: drive the real Streamlit page with the fake LLM."""
import pytest
from streamlit.testing.v1 import AppTest

import main
from conftest import REQUEST, ROOT, TAILORED_RESUME, FakeEmbedder, fake_llm

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
        "Tailored resume", "Recruiter snapshot", "Cover letter", "Interview prep", "ATS analysis",
        "Review suggestions", "First draft",
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
    def down(prompt, **kwargs):
        raise main.LLMUnavailableError("down")

    monkeypatch.setattr(main, "call_llm", down)
    at = generate(app)
    assert any("temporarily unavailable" in e.value for e in at.error)
    assert at.session_state.generation_count == 0


def test_broken_resume_output_shows_error(app, monkeypatch):
    def broken(prompt, **kwargs):
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


def metric_value(at, label):
    return next(m.value for m in at.metric if m.label == label)


def test_score_updates_live_after_adding_a_skill(app):
    at = generate(app)
    before = metric_value(at, "ATS match")
    at.pills(key="have_skill_0").set_value("Kubernetes").run()
    assert "Additional Skills: Kubernetes" in at.session_state.docs["resume"]
    assert metric_value(at, "ATS match") != before
    assert not at.exception


def test_score_updates_live_after_editing(app):
    at = generate(app)
    before = metric_value(at, "ATS match")
    at.segmented_control(key="mode_resume").set_value("Edit").run()
    editor = next(t for t in at.text_area if t.key and t.key.startswith("editor_resume_"))
    editor.set_value(TAILORED_RESUME + "\nTOOLS\nKubernetes").run()
    assert metric_value(at, "ATS match") != before
    assert not any(p.key and p.key.startswith("have_skill_") for p in at.pills)  # nothing missing any more
    assert not at.exception


def test_interview_prep_on_demand(app, monkeypatch):
    def llm(prompt, **kwargs):
        if "hiring manager preparing to interview" in prompt:
            return ('[{"category": "Technical", "question": "How did you scale your APIs?", "why_they_ask": "Core skill.", '
                    '"answer": {"situation": "TechCorp", "task": "Scale", "action": "FastAPI", "result": "1M+ requests"}}]')
        return fake_llm(prompt)

    at = generate(app)
    monkeypatch.setattr(main, "call_llm", llm)
    button(at, "Generate interview prep").click().run()
    assert at.session_state.interview_prep["questions"][0]["question"] == "How did you scale your APIs?"
    assert any("How did you scale your APIs?" in e.label for e in at.expander)
    assert at.session_state.generation_count == 1  # on-demand extras don't use up generations


def test_cover_letter_tone_rewrite(app, monkeypatch):
    def llm(prompt, **kwargs):
        if "cover letter" in prompt and "Warm, personable" in prompt:
            return "Hi there,\n\nFriendly letter.\n\nBest,\nJordan Lee"
        return fake_llm(prompt)

    at = generate(app)
    monkeypatch.setattr(main, "call_llm", llm)
    at.segmented_control(key="tone_choice").set_value("Friendly").run()
    button(at, "Rewrite as friendly").click().run()
    assert at.session_state.docs["cover_letter"].startswith("Hi there")
    assert at.session_state.letter_tone == "Friendly"


def test_busy_message_when_rate_limited(app, monkeypatch):
    def busy(prompt, **kwargs):
        raise main.LLMBusyError("limit", daily=True)

    monkeypatch.setattr(main, "call_llm", busy)
    at = generate(app)
    assert any("very busy right now" in w.value and "later today" in w.value for w in at.warning)
    assert at.session_state.generation_count == 0


def test_feedback_is_recorded_once(app, monkeypatch):
    import ui_common
    sent = []
    monkeypatch.setattr(ui_common, "_bump", sent.append)
    at = generate(app)
    at.feedback[0].set_value(1).run()
    at.run()
    assert sent.count("feedback-helpful") == 1


@pytest.mark.parametrize("page", ["app_pages/how_we_score.py", "app_pages/privacy.py", "app_pages/compare.py"])
def test_other_pages_render(app, page):
    app.switch_page(page).run()
    assert not app.exception


def test_compare_jobs_ranks_and_hands_off_to_tailor(app, monkeypatch):
    def llm(prompt, **kwargs):
        if '"job_keywords"' in prompt and "Rust" in prompt:
            return '{"job_keywords": ["Rust", "Go", "Kubernetes"], "explanation": "Different stack."}'
        return fake_llm(prompt)

    monkeypatch.setattr(main, "call_llm", llm)
    at = generate(app)
    at.switch_page("app_pages/compare.py").run()
    at.text_area(key="compare_jd_0").set_value("Systems engineer: Rust, Go, Kubernetes").run()
    at.text_area(key="compare_jd_1").set_value(REQUEST["job_description"]).run()
    button(at, "Compare jobs").click().run()
    ranking = at.session_state.comparison
    assert [r["index"] for r in ranking] == [1, 0]  # the Python/FastAPI job fits best
    assert not at.exception
    button(at, "Tailor for this job").click().run()
    assert at.session_state.job_description_area == REQUEST["job_description"]
