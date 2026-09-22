"""
Turns plain-text resumes and cover letters into professionally formatted documents.

A single parser (parse_resume) classifies each line, and three renderers share it so the
on-screen preview, the PDF, and the DOCX always look alike. Each renderer takes a template
name from TEMPLATES, which controls typography, color, alignment, and density.
"""
import html
import io
import re

MUTED_RGB = (100, 110, 125)
TEXT_RGB = (17, 24, 39)

# Every template field is used by all three renderers (HTML preview, PDF, DOCX).
TEMPLATES = {
    "Professional": {
        "description": "Centered header, navy accents, clean sans-serif.",
        "accent": (30, 58, 138), "align": "C", "heading": "rule",
        "pdf_font": "Helvetica", "docx_font": "Calibri", "html_font": "Inter, Helvetica, Arial, sans-serif",
        "name_size": 20, "body_size": 9.8, "heading_size": 10.5, "line": 5.0, "margin": 18, "gap": 3.5,
    },
    "Modern": {
        "description": "Left-aligned header, teal accent bars, contemporary feel.",
        "accent": (15, 118, 110), "align": "L", "heading": "bar",
        "pdf_font": "Helvetica", "docx_font": "Calibri", "html_font": "Inter, Helvetica, Arial, sans-serif",
        "name_size": 22, "body_size": 9.8, "heading_size": 10.5, "line": 5.0, "margin": 18, "gap": 4.0,
    },
    "Classic": {
        "description": "Traditional serif typography in charcoal — ideal for finance, law, and academia.",
        "accent": (31, 41, 55), "align": "C", "heading": "rule",
        "pdf_font": "Times", "docx_font": "Georgia", "html_font": "Georgia, 'Times New Roman', serif",
        "name_size": 21, "body_size": 10.5, "heading_size": 11, "line": 5.2, "margin": 20, "gap": 3.5,
    },
    "Compact": {
        "description": "Smaller type and tighter spacing to fit more on one page.",
        "accent": (30, 58, 138), "align": "C", "heading": "rule",
        "pdf_font": "Helvetica", "docx_font": "Calibri", "html_font": "Inter, Helvetica, Arial, sans-serif",
        "name_size": 16, "body_size": 8.8, "heading_size": 9.5, "line": 4.3, "margin": 12, "gap": 2.2,
    },
}
DEFAULT_TEMPLATE = "Professional"


def _template(name: str | None) -> dict:
    return TEMPLATES.get(name or DEFAULT_TEMPLATE, TEMPLATES[DEFAULT_TEMPLATE])


def _hex(rgb) -> str:
    return "#%02X%02X%02X" % rgb


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

def _html_vars(t: dict) -> str:
    return (
        f"--doc-accent:{_hex(t['accent'])};--doc-font:{t['html_font']};"
        f"--doc-align:{'left' if t['align'] == 'L' else 'center'};"
        f"--doc-size:{t['body_size'] / 9.8 * 0.9:.3f}rem;"
    )


def resume_to_html(text: str, template: str | None = None) -> str:
    t = _template(template)
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
            parts.append(f'<div class="cl-heading cl-heading-{t["heading"]}">{safe}</div>')
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
    return f'<div class="cl-doc" style="{_html_vars(t)}">' + "".join(parts) + "</div>"


def letter_to_html(text: str, template: str | None = None) -> str:
    t = _template(template)
    paragraphs = "".join(
        "<p>" + html.escape(p).replace("\n", "<br>") + "</p>" for p in parse_letter(text)
    )
    return f'<div class="cl-doc cl-letter" style="{_html_vars(t)}">{paragraphs}</div>'

# ------------------------------------------------------------------
# PDF (fpdf2, core fonts)
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


def _new_pdf(margin: float):
    from fpdf import FPDF

    pdf = FPDF(format="Letter")
    pdf.set_margins(margin, margin * 0.9, margin)
    pdf.set_auto_page_break(auto=True, margin=margin * 0.9)
    pdf.add_page()
    pdf.set_text_color(*TEXT_RGB)
    return pdf


def build_resume_pdf(text: str, template: str | None = None) -> bytes:
    t = _template(template)
    font, body, line = t["pdf_font"], t["body_size"], t["line"]
    pdf = _new_pdf(t["margin"])
    width = pdf.w - pdf.l_margin - pdf.r_margin

    for kind, value in parse_resume(text):
        value = _pdf_safe(value)
        pdf.set_x(pdf.l_margin)
        if kind == "name":
            pdf.set_font(font, "B", t["name_size"])
            pdf.set_text_color(*t["accent"])
            pdf.cell(width, t["name_size"] * 0.5, value, align=t["align"], new_x="LMARGIN", new_y="NEXT")
            pdf.set_text_color(*TEXT_RGB)
        elif kind == "contact":
            pdf.set_font(font, "", body - 0.8)
            pdf.set_text_color(*MUTED_RGB)
            pdf.multi_cell(width, line - 0.4, value, align=t["align"], new_x="LMARGIN", new_y="NEXT")
            pdf.set_text_color(*TEXT_RGB)
        elif kind == "heading":
            pdf.ln(t["gap"])
            pdf.set_font(font, "B", t["heading_size"])
            pdf.set_text_color(*t["accent"])
            if t["heading"] == "bar":
                y = pdf.get_y()
                pdf.set_fill_color(*t["accent"])
                pdf.rect(pdf.l_margin, y + 0.8, 1.2, t["heading_size"] * 0.42, style="F")
                pdf.set_x(pdf.l_margin + 3.5)
                pdf.cell(width - 3.5, line + 1, value, new_x="LMARGIN", new_y="NEXT")
                pdf.ln(0.8)
            else:
                pdf.cell(width, line + 1, value, new_x="LMARGIN", new_y="NEXT")
                pdf.set_draw_color(*t["accent"])
                pdf.set_line_width(0.35)
                pdf.line(pdf.l_margin, pdf.get_y(), pdf.l_margin + width, pdf.get_y())
                pdf.ln(t["gap"] * 0.5)
            pdf.set_text_color(*TEXT_RGB)
        elif kind == "entry":
            pdf.ln(t["gap"] * 0.35)
            pdf.set_font(font, "B", body + 0.2)
            pdf.multi_cell(width, line + 0.2, value, new_x="LMARGIN", new_y="NEXT")
        elif kind == "bullet":
            pdf.set_font(font, "", body)
            y = pdf.get_y()
            pdf.set_fill_color(*TEXT_RGB)
            pdf.ellipse(pdf.l_margin + 1.6, y + line * 0.41, 1.1, 1.1, style="F")
            pdf.set_x(pdf.l_margin + 5)
            pdf.multi_cell(width - 5, line, value, new_x="LMARGIN", new_y="NEXT")
        elif kind == "label":
            label, rest = _LABEL_RE.match(value).groups()
            pdf.set_font(font, "B", body)
            pdf.write(line, f"{label}: ")
            pdf.set_font(font, "", body)
            pdf.write(line, rest)
            pdf.ln(line)
        else:
            pdf.set_font(font, "", body)
            pdf.multi_cell(width, line, value, new_x="LMARGIN", new_y="NEXT")

    return bytes(pdf.output())


def build_letter_pdf(text: str, sender_name: str = "", template: str | None = None) -> bytes:
    t = _template(template)
    font = t["pdf_font"]
    pdf = _new_pdf(25)
    width = pdf.w - pdf.l_margin - pdf.r_margin

    if sender_name:
        pdf.set_x(pdf.l_margin)
        pdf.set_font(font, "B", 16)
        pdf.set_text_color(*t["accent"])
        pdf.cell(width, 9, _pdf_safe(sender_name), new_x="LMARGIN", new_y="NEXT")
        pdf.set_draw_color(*t["accent"])
        pdf.set_line_width(0.35)
        pdf.line(pdf.l_margin, pdf.get_y() + 1, pdf.l_margin + width, pdf.get_y() + 1)
        pdf.ln(9)
        pdf.set_text_color(*TEXT_RGB)

    pdf.set_font(font, "", 10.5 if font != "Times" else 11.5)
    for paragraph in parse_letter(text):
        pdf.set_x(pdf.l_margin)
        pdf.multi_cell(width, 5.6, _pdf_safe(paragraph), new_x="LMARGIN", new_y="NEXT")
        pdf.ln(3.5)

    return bytes(pdf.output())

# ------------------------------------------------------------------
# DOCX (python-docx)
# ------------------------------------------------------------------

def _new_docx(margin_inches: float, t: dict):
    import docx
    from docx.shared import Inches, Pt, RGBColor

    document = docx.Document()
    for section in document.sections:
        section.left_margin = section.right_margin = Inches(margin_inches)
        section.top_margin = section.bottom_margin = Inches(min(margin_inches, 0.6))
    normal = document.styles["Normal"]
    normal.font.name = t["docx_font"]
    normal.font.size = Pt(t["body_size"] + 0.7)
    normal.font.color.rgb = RGBColor(*TEXT_RGB)
    normal.paragraph_format.space_after = Pt(2 if t["gap"] >= 3 else 1)
    return document


def _add_border(paragraph, side: str, color_rgb, size: int = 6):
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    p_pr = paragraph._p.get_or_add_pPr()
    borders = OxmlElement("w:pBdr")
    edge = OxmlElement(f"w:{side}")
    edge.set(qn("w:val"), "single")
    edge.set(qn("w:sz"), str(size))
    edge.set(qn("w:space"), "4" if side == "left" else "1")
    edge.set(qn("w:color"), "%02X%02X%02X" % color_rgb)
    borders.append(edge)
    p_pr.append(borders)


def _docx_bytes(document) -> bytes:
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def build_resume_docx(text: str, template: str | None = None) -> bytes:
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Pt, RGBColor

    t = _template(template)
    align = WD_ALIGN_PARAGRAPH.LEFT if t["align"] == "L" else WD_ALIGN_PARAGRAPH.CENTER
    document = _new_docx(t["margin"] / 25.4, t)
    for kind, value in parse_resume(text):
        if kind == "name":
            p = document.add_paragraph()
            p.alignment = align
            run = p.add_run(value)
            run.bold = True
            run.font.size = Pt(t["name_size"])
            run.font.color.rgb = RGBColor(*t["accent"])
        elif kind == "contact":
            p = document.add_paragraph()
            p.alignment = align
            run = p.add_run(value)
            run.font.size = Pt(t["body_size"] - 0.8)
            run.font.color.rgb = RGBColor(*MUTED_RGB)
        elif kind == "heading":
            p = document.add_paragraph()
            p.paragraph_format.space_before = Pt(t["gap"] * 2.8)
            p.paragraph_format.space_after = Pt(4)
            run = p.add_run(value)
            run.bold = True
            run.font.size = Pt(t["heading_size"] + 0.5)
            run.font.color.rgb = RGBColor(*t["accent"])
            if t["heading"] == "bar":
                _add_border(p, "left", t["accent"], size=18)
            else:
                _add_border(p, "bottom", t["accent"])
        elif kind == "entry":
            p = document.add_paragraph()
            p.paragraph_format.space_before = Pt(t["gap"])
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


def build_letter_docx(text: str, sender_name: str = "", template: str | None = None) -> bytes:
    from docx.shared import Pt, RGBColor

    t = _template(template)
    document = _new_docx(1.0, t)
    if sender_name:
        p = document.add_paragraph()
        p.paragraph_format.space_after = Pt(14)
        run = p.add_run(sender_name)
        run.bold = True
        run.font.size = Pt(16)
        run.font.color.rgb = RGBColor(*t["accent"])
        _add_border(p, "bottom", t["accent"])
    for paragraph in parse_letter(text):
        p = document.add_paragraph()
        p.paragraph_format.space_after = Pt(10)
        lines = paragraph.split("\n")
        for i, line in enumerate(lines):
            run = p.add_run(line)
            if i < len(lines) - 1:
                run.add_break()
    return _docx_bytes(document)
