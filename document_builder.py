"""
Turns plain-text resumes and cover letters into professionally formatted documents.

A single parser (parse_resume) classifies each line, and three renderers share it so the
on-screen preview, the PDF, and the DOCX always look alike.
"""
import html
import io
import re

ACCENT_RGB = (30, 58, 138)     # CareerLoom navy
MUTED_RGB = (100, 110, 125)
TEXT_RGB = (17, 24, 39)

_BULLET_RE = re.compile(r"^\s*(?:[-*•–●▪]|\d+[.)])\s+")
_LABEL_RE = re.compile(r"^([A-Z][A-Za-z0-9 &/+.,()-]{1,40}):\s+(.+)$")
_YEAR_RE = re.compile(r"\b(?:19|20)\d{2}\b|\bPresent\b", re.IGNORECASE)


def _strip_markdown(line: str) -> str:
    line = re.sub(r"^\s*#{1,6}\s*", "", line)
    line = line.replace("**", "").replace("__", "").replace("`", "")
    return line.strip()


def _is_heading(raw: str, clean: str) -> bool:
    if re.match(r"^\s*#{1,6}\s+", raw):
        return True
    letters = [c for c in clean if c.isalpha()]
    return (
        3 <= len(letters)
        and len(clean) <= 45
        and clean.rstrip(":").upper() == clean.rstrip(":")
        and not _BULLET_RE.match(clean)
    )


def parse_resume(text: str) -> list[tuple[str, str]]:
    """
    Classify each line as one of: name, contact, heading, entry, bullet, label, text.
    Returns (kind, text) pairs; blank lines and markdown rules are dropped.
    """
    blocks = []
    seen_heading = False
    for raw in (text or "").splitlines():
        clean = _strip_markdown(raw)
        if not clean or set(clean) <= set("-=_*"):
            continue

        if not blocks:
            blocks.append(("name", clean))
        elif not seen_heading and not _is_heading(raw, clean):
            blocks.append(("contact", clean))
        elif _is_heading(raw, clean):
            seen_heading = True
            blocks.append(("heading", clean.rstrip(":").upper()))
        elif _BULLET_RE.match(clean):
            blocks.append(("bullet", _BULLET_RE.sub("", clean, count=1)))
        elif _LABEL_RE.match(clean):
            blocks.append(("label", clean))
        elif _YEAR_RE.search(clean) and ("|" in clean or len(clean) <= 90):
            blocks.append(("entry", clean))
        else:
            blocks.append(("text", clean))
    return blocks


def parse_letter(text: str) -> list[str]:
    """Split a cover letter into paragraphs, keeping single line breaks inside short blocks (sign-off)."""
    paragraphs = re.split(r"\n\s*\n", _strip_markdown_block(text or ""))
    return [p.strip() for p in paragraphs if p.strip()]


def _strip_markdown_block(text: str) -> str:
    return "\n".join(_strip_markdown(line) if line.strip() else "" for line in text.splitlines())

# ------------------------------------------------------------------
# HTML preview (rendered inside the Streamlit page)
# ------------------------------------------------------------------

def resume_to_html(text: str) -> str:
    parts = []
    in_list = False
    for kind, value in parse_resume(text):
        if kind != "bullet" and in_list:
            parts.append("</ul>")
            in_list = False
        safe = html.escape(value)
        if kind == "name":
            parts.append(f'<div class="cl-name">{safe}</div>')
        elif kind == "contact":
            parts.append(f'<div class="cl-contact">{safe}</div>')
        elif kind == "heading":
            parts.append(f'<div class="cl-heading">{safe}</div>')
        elif kind == "entry":
            parts.append(f'<div class="cl-entry">{safe}</div>')
        elif kind == "bullet":
            if not in_list:
                parts.append("<ul>")
                in_list = True
            parts.append(f"<li>{safe}</li>")
        elif kind == "label":
            label, rest = _LABEL_RE.match(value).groups()
            parts.append(f'<p><strong>{html.escape(label)}:</strong> {html.escape(rest)}</p>')
        else:
            parts.append(f"<p>{safe}</p>")
    if in_list:
        parts.append("</ul>")
    return '<div class="cl-doc">' + "".join(parts) + "</div>"


def letter_to_html(text: str) -> str:
    paragraphs = "".join(
        "<p>" + html.escape(p).replace("\n", "<br>") + "</p>" for p in parse_letter(text)
    )
    return f'<div class="cl-doc cl-letter">{paragraphs}</div>'

# ------------------------------------------------------------------
# PDF (fpdf2, core Helvetica font)
# ------------------------------------------------------------------

_LATIN1_REPLACEMENTS = {
    "—": "-", "–": "-", "‐": "-", "‑": "-", "‘": "'", "’": "'",
    "“": '"', "”": '"', "•": "-", "…": "...",
    " ": " ", "●": "-", "▪": "-",
}


def _pdf_safe(text: str) -> str:
    # Core PDF fonts only support latin-1 — sanitize common unicode punctuation.
    for old, new in _LATIN1_REPLACEMENTS.items():
        text = text.replace(old, new)
    text = text.encode("latin-1", errors="replace").decode("latin-1")
    # fpdf2 can't wrap a single "word" wider than the line (e.g. a long URL) — pre-break those.
    return " ".join(
        " ".join(w[i:i + 50] for i in range(0, len(w), 50)) if len(w) > 50 else w
        for w in text.split(" ")
    )


def _new_pdf():
    from fpdf import FPDF

    pdf = FPDF(format="Letter")
    pdf.set_margins(18, 16, 18)
    pdf.set_auto_page_break(auto=True, margin=16)
    pdf.add_page()
    pdf.set_text_color(*TEXT_RGB)
    return pdf


def build_resume_pdf(text: str) -> bytes:
    pdf = _new_pdf()
    width = pdf.w - pdf.l_margin - pdf.r_margin

    for kind, value in parse_resume(text):
        value = _pdf_safe(value)
        pdf.set_x(pdf.l_margin)
        if kind == "name":
            pdf.set_font("Helvetica", "B", 20)
            pdf.set_text_color(*ACCENT_RGB)
            pdf.cell(width, 10, value, align="C", new_x="LMARGIN", new_y="NEXT")
            pdf.set_text_color(*TEXT_RGB)
        elif kind == "contact":
            pdf.set_font("Helvetica", "", 9)
            pdf.set_text_color(*MUTED_RGB)
            pdf.multi_cell(width, 4.6, value, align="C", new_x="LMARGIN", new_y="NEXT")
            pdf.set_text_color(*TEXT_RGB)
        elif kind == "heading":
            pdf.ln(3.5)
            pdf.set_font("Helvetica", "B", 10.5)
            pdf.set_text_color(*ACCENT_RGB)
            pdf.cell(width, 6, value, new_x="LMARGIN", new_y="NEXT")
            pdf.set_draw_color(*ACCENT_RGB)
            pdf.set_line_width(0.35)
            pdf.line(pdf.l_margin, pdf.get_y(), pdf.l_margin + width, pdf.get_y())
            pdf.ln(1.8)
            pdf.set_text_color(*TEXT_RGB)
        elif kind == "entry":
            pdf.ln(1.2)
            pdf.set_font("Helvetica", "B", 10)
            pdf.multi_cell(width, 5.2, value, new_x="LMARGIN", new_y="NEXT")
        elif kind == "bullet":
            pdf.set_font("Helvetica", "", 9.8)
            y = pdf.get_y()
            pdf.set_fill_color(*TEXT_RGB)
            pdf.ellipse(pdf.l_margin + 1.6, y + 2.05, 1.1, 1.1, style="F")
            pdf.set_x(pdf.l_margin + 5)
            pdf.multi_cell(width - 5, 5, value, new_x="LMARGIN", new_y="NEXT")
        elif kind == "label":
            label, rest = _LABEL_RE.match(value).groups()
            pdf.set_font("Helvetica", "B", 9.8)
            pdf.write(5, f"{label}: ")
            pdf.set_font("Helvetica", "", 9.8)
            pdf.write(5, rest)
            pdf.ln(5)
        else:
            pdf.set_font("Helvetica", "", 9.8)
            pdf.multi_cell(width, 5, value, new_x="LMARGIN", new_y="NEXT")

    return bytes(pdf.output())


def build_letter_pdf(text: str, sender_name: str = "") -> bytes:
    pdf = _new_pdf()
    pdf.set_margins(25, 22, 25)
    pdf.set_y(22)
    width = pdf.w - pdf.l_margin - pdf.r_margin

    if sender_name:
        pdf.set_x(pdf.l_margin)
        pdf.set_font("Helvetica", "B", 16)
        pdf.set_text_color(*ACCENT_RGB)
        pdf.cell(width, 9, _pdf_safe(sender_name), new_x="LMARGIN", new_y="NEXT")
        pdf.set_draw_color(*ACCENT_RGB)
        pdf.set_line_width(0.35)
        pdf.line(pdf.l_margin, pdf.get_y() + 1, pdf.l_margin + width, pdf.get_y() + 1)
        pdf.ln(9)
        pdf.set_text_color(*TEXT_RGB)

    pdf.set_font("Helvetica", "", 10.5)
    for paragraph in parse_letter(text):
        pdf.set_x(pdf.l_margin)
        pdf.multi_cell(width, 5.6, _pdf_safe(paragraph), new_x="LMARGIN", new_y="NEXT")
        pdf.ln(3.5)

    return bytes(pdf.output())

# ------------------------------------------------------------------
# DOCX (python-docx)
# ------------------------------------------------------------------

def _new_docx(margin_inches: float):
    import docx
    from docx.shared import Inches, Pt, RGBColor

    document = docx.Document()
    for section in document.sections:
        section.left_margin = section.right_margin = Inches(margin_inches)
        section.top_margin = section.bottom_margin = Inches(0.6)
    normal = document.styles["Normal"]
    normal.font.name = "Calibri"
    normal.font.size = Pt(10.5)
    normal.font.color.rgb = RGBColor(*TEXT_RGB)
    normal.paragraph_format.space_after = Pt(2)
    return document


def _add_bottom_border(paragraph):
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    p_pr = paragraph._p.get_or_add_pPr()
    borders = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"), "single")
    bottom.set(qn("w:sz"), "6")
    bottom.set(qn("w:space"), "1")
    bottom.set(qn("w:color"), "%02X%02X%02X" % ACCENT_RGB)
    borders.append(bottom)
    p_pr.append(borders)


def _docx_bytes(document) -> bytes:
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def build_resume_docx(text: str) -> bytes:
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Pt, RGBColor

    document = _new_docx(0.75)
    for kind, value in parse_resume(text):
        if kind == "name":
            p = document.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            run = p.add_run(value)
            run.bold = True
            run.font.size = Pt(20)
            run.font.color.rgb = RGBColor(*ACCENT_RGB)
        elif kind == "contact":
            p = document.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            run = p.add_run(value)
            run.font.size = Pt(9)
            run.font.color.rgb = RGBColor(*MUTED_RGB)
        elif kind == "heading":
            p = document.add_paragraph()
            p.paragraph_format.space_before = Pt(10)
            p.paragraph_format.space_after = Pt(4)
            run = p.add_run(value)
            run.bold = True
            run.font.size = Pt(11)
            run.font.color.rgb = RGBColor(*ACCENT_RGB)
            _add_bottom_border(p)
        elif kind == "entry":
            p = document.add_paragraph()
            p.paragraph_format.space_before = Pt(4)
            p.add_run(value).bold = True
        elif kind == "bullet":
            document.add_paragraph(value, style="List Bullet")
        elif kind == "label":
            label, rest = _LABEL_RE.match(value).groups()
            p = document.add_paragraph()
            p.add_run(f"{label}: ").bold = True
            p.add_run(rest)
        else:
            document.add_paragraph(value)
    return _docx_bytes(document)


def build_letter_docx(text: str, sender_name: str = "") -> bytes:
    from docx.shared import Pt, RGBColor

    document = _new_docx(1.0)
    if sender_name:
        p = document.add_paragraph()
        p.paragraph_format.space_after = Pt(14)
        run = p.add_run(sender_name)
        run.bold = True
        run.font.size = Pt(16)
        run.font.color.rgb = RGBColor(*ACCENT_RGB)
        _add_bottom_border(p)
    for paragraph in parse_letter(text):
        p = document.add_paragraph()
        p.paragraph_format.space_after = Pt(10)
        lines = paragraph.split("\n")
        for i, line in enumerate(lines):
            run = p.add_run(line)
            if i < len(lines) - 1:
                run.add_break()
    return _docx_bytes(document)
