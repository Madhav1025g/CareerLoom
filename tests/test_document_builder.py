import io

import pytest

from conftest import SNAPSHOT, SOURCE_RESUME
from document_builder import (
    TEMPLATES,
    build_letter_docx,
    build_letter_pdf,
    build_resume_docx,
    build_resume_pdf,
    letter_to_html,
    parse_letter,
    parse_resume,
    resume_to_html,
)

LETTER = "Dear Hiring Manager,\n\nI am excited — truly — to apply.\n\nSincerely,\nJordan Lee"


def kinds(text):
    return [kind for kind, _ in parse_resume(text)]


def test_parse_resume_classifies_lines():
    blocks = dict(parse_resume(SOURCE_RESUME))
    assert parse_resume(SOURCE_RESUME)[0] == ("name", "Jordan Lee")
    assert "contact" in kinds(SOURCE_RESUME)
    assert ("heading", "EXPERIENCE") in parse_resume(SOURCE_RESUME)
    assert ("entry", "Software Engineer | TechCorp Inc. | Remote | Jan 2021 - Present") in parse_resume(SOURCE_RESUME)
    assert ("label", "Languages: Python, JavaScript, SQL") in parse_resume(SOURCE_RESUME)
    assert blocks  # sanity


def test_parse_resume_strips_markdown():
    blocks = parse_resume("**Jordan Lee**\n## EXPERIENCE\n* Built things")
    assert blocks == [("name", "Jordan Lee"), ("heading", "EXPERIENCE"), ("bullet", "Built things")]


def test_parse_letter_keeps_signoff_together():
    assert parse_letter(LETTER)[-1] == "Sincerely,\nJordan Lee"


def test_html_escapes_user_content():
    html = resume_to_html(SOURCE_RESUME + "\n<script>alert(1)</script>")
    assert "<script>" not in html and "&lt;script&gt;" in html


@pytest.mark.parametrize("template", list(TEMPLATES))
@pytest.mark.parametrize("text", [SOURCE_RESUME, SNAPSHOT, "", "Name only"])
def test_resume_exports_for_every_template(template, text):
    assert build_resume_pdf(text, template).startswith(b"%PDF")
    assert build_resume_docx(text, template).startswith(b"PK")
    assert "cl-doc" in resume_to_html(text, template)


@pytest.mark.parametrize("template", list(TEMPLATES))
def test_letter_exports_for_every_template(template):
    assert build_letter_pdf(LETTER, "Jordan Lee", template).startswith(b"%PDF")
    assert build_letter_docx(LETTER, "Jordan Lee", template).startswith(b"PK")
    assert "cl-letter" in letter_to_html(LETTER, template)


def test_pdf_handles_unicode_and_long_words():
    text = "Jordan Lee\nEXPERIENCE\n- cloud‑native “quoted” work — café \U0001F680 " + "x" * 300
    assert build_resume_pdf(text).startswith(b"%PDF")


def test_templates_change_the_output():
    pdfs = {name: build_resume_pdf(SOURCE_RESUME, name) for name in TEMPLATES}
    assert len(set(pdfs.values())) == len(TEMPLATES)


def test_docx_content_round_trips():
    import docx

    document = docx.Document(io.BytesIO(build_resume_docx(SOURCE_RESUME, "Modern")))
    text = "\n".join(p.text for p in document.paragraphs)
    assert "Jordan Lee" in text and "TechCorp" in text and "EXPERIENCE" in text


def test_unknown_template_falls_back_to_default():
    assert build_resume_pdf(SOURCE_RESUME, "Nope").startswith(b"%PDF")
