"""Unit tests for the shared UI helpers: score bands, verdict fixes, progress stages, upload checks."""
import pytest

import main
from conftest import TAILORED_RESUME
from document_builder import build_resume_pdf, pdf_page_count
from ui_common import (
    PROGRESS_STAGES, SCORE_BANDS, progress_stage, score_band, step_tracker_html, text_quality_issues, top_fixes,
)


@pytest.mark.parametrize("score, label", [(100, "Strong match"), (80, "Strong match"), (79, "Good match"),
                                          (67, "Good match"), (64, "Fair match"), (45, "Fair match"),
                                          (44, "Stretch role"), (0, "Stretch role")])
def test_score_bands(score, label):
    assert score_band(score)[0] == label
    assert [b[0] for b in SCORE_BANDS] == sorted((b[0] for b in SCORE_BANDS), reverse=True)


def item(i, status, importance="required", category="skill", weight=3.0):
    return {"id": f"r{i}", "text": f"req {i}", "status": status, "importance": importance,
            "category": category, "weight": weight}


def test_top_fixes_orders_required_and_missing_first():
    items = [item(1, "met"), item(2, "partial", "preferred", weight=1.0), item(3, "partial"),
             item(4, "not_met", "preferred", weight=1.0), item(5, "not_met"),
             item(6, "not_met", "required", "soft_skill", 0.5)]
    assert [i["id"] for i in top_fixes(items)] == ["r5", "r3", "r4"]  # soft skills and met items are never "fixes"
    assert top_fixes([item(1, "met")]) == []


def test_every_orchestrator_message_maps_to_a_stage():
    import inspect
    import re
    messages = re.findall(r'notify\("([^"]+)"\)', inspect.getsource(main.orchestrator))
    assert len(messages) >= 8
    stages = [progress_stage(m) for m in messages]
    assert stages == sorted(stages), "messages should move forward through the stages"
    assert stages[0] == 0 and stages[-1] == len(PROGRESS_STAGES) - 1
    assert progress_stage("Something new", current=2) == 2  # unknown -> stay put
    assert progress_stage("Reading your resume...", current=3) == 3  # never go backwards


def test_step_tracker_states():
    html = step_tracker_html(2)
    assert html.count("cl-step-done") == 2 and html.count("cl-step-active") == 1
    assert step_tracker_html(0, done=True).count("cl-step-done") == len(PROGRESS_STAGES)


def test_clean_resume_has_no_quality_issues():
    assert text_quality_issues(TAILORED_RESUME * 2) == []


def test_quality_issues_are_detected():
    assert any("only" in i for i in text_quality_issues("Jordan Lee\nPython"))
    assert any("characters didn't come through" in i for i in text_quality_issues(TAILORED_RESUME + "(cid:12)" * 6))
    spaced = TAILORED_RESUME + "\nS k i l l s P y t h o n\nE x p e r i e n c e\nA W S D o c k e r"
    assert any("spaces between the letters" in i for i in text_quality_issues(spaced))
    fragments = "EXPERIENCE\n" + "\n".join(["Python", "2021", "AWS", "Lead"] * 10) + "\n" + "x" * 400
    assert any("short fragments" in i for i in text_quality_issues(fragments))
    assert any("standard sections" in i for i in text_quality_issues("Lorem ipsum dolor sit amet. " * 30))


def test_pdf_page_count():
    assert pdf_page_count(build_resume_pdf(TAILORED_RESUME)) == 1
    long_resume = TAILORED_RESUME + "\nPROJECTS\n" + "\n".join(f"- Project {i}: built a data pipeline" for i in range(90))
    assert pdf_page_count(build_resume_pdf(long_resume)) >= 2
    assert pdf_page_count(b"not a pdf") == 1
