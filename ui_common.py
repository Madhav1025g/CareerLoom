"""Shared styling, layout pieces, and helpers used by every CareerLoom page."""
import html
import re

import requests
import streamlit as st

from main import APP_NAME

CSS = """<style>
/* Every color is a light/dark pair. Streamlit sets color-scheme on the app to match the active theme
   (the user's system setting, or Settings > Theme), so light-dark() always picks the right one. */
.stApp, header[data-testid="stHeader"] {
  --cl-ink: light-dark(#0F172A, #F1F5F9);
  --cl-body: light-dark(#334155, #CBD5E1);
  --cl-muted: light-dark(#64748B, #94A3B8);
  --cl-faint: light-dark(#94A3B8, #64748B);
  --cl-border: light-dark(#E3E7EF, #2A3140);
  --cl-divider: light-dark(#EEF1F5, #222938);
  --cl-surface: light-dark(#FAFBFD, #151A24);
  --cl-accent: light-dark(#1E3A8A, #8DA8F0);
  --cl-accent-fill: light-dark(#1E3A8A, #3B5BDB);
  --cl-accent-soft: light-dark(#EEF2FF, #1A2340);
  --cl-accent-line: light-dark(#DCE3F9, #2C3A66);
  --cl-eyebrow: light-dark(#B45309, #F5B354);
  --cl-good: light-dark(#166534, #86EFAC);  --cl-good-bg: light-dark(#F0FDF4, #0F2A1A);  --cl-good-line: light-dark(#BBF7D0, #1F5133);
  --cl-warn: light-dark(#92400E, #FCD34D);  --cl-warn-bg: light-dark(#FFFBEB, #2B2310);  --cl-warn-line: light-dark(#FDE68A, #5C4813);
  --cl-bad: light-dark(#991B1B, #FCA5A5);   --cl-bad-bg: light-dark(#FEF2F2, #2D1414);   --cl-bad-line: light-dark(#FECACA, #5E2424);
  --cl-chip: light-dark(#9A3412, #FDBA74);  --cl-chip-bg: light-dark(#FFF7ED, #2B1A0E);  --cl-chip-line: light-dark(#FED7AA, #5C3417);
}
.block-container { max-width: 1140px; padding-top: 2.2rem; padding-bottom: 3rem; }
/* Top navigation bar: solid so page content never shows through it while scrolling */
header[data-testid="stHeader"] { background: light-dark(rgba(255, 255, 255, 0.97), rgba(14, 17, 23, 0.97));
                                 border-bottom: 1px solid var(--cl-border); backdrop-filter: blur(6px); }

.cl-hero { padding: 0.5rem 0 1.8rem 0; max-width: 780px; }
.cl-eyebrow { text-transform: uppercase; letter-spacing: 0.12em; font-size: 0.75rem; font-weight: 700; color: var(--cl-eyebrow); margin-bottom: 0.7rem; }
.cl-h1 { font-size: 2.6rem; line-height: 1.12; font-weight: 700; color: var(--cl-ink); letter-spacing: -0.025em; margin-bottom: 0.9rem; }
.cl-lead { font-size: 1.08rem; line-height: 1.6; color: var(--cl-muted); }

.cl-features { display: grid; grid-template-columns: repeat(auto-fit, minmax(230px, 1fr)); gap: 1rem; margin-bottom: 2.6rem; }
.cl-feature { border: 1px solid var(--cl-border); border-radius: 12px; padding: 1.1rem 1.2rem; background: var(--cl-surface); }
.cl-feature-title { font-weight: 600; color: var(--cl-ink); margin-bottom: 0.3rem; }
.cl-feature-text { font-size: 0.9rem; color: var(--cl-muted); line-height: 1.5; }

.cl-section-title { font-size: 1.45rem; font-weight: 700; color: var(--cl-ink); letter-spacing: -0.015em; margin: 0.4rem 0 0.2rem 0; }
.cl-section-sub { color: var(--cl-muted); font-size: 0.95rem; margin-bottom: 1rem; }
.cl-card-title { font-weight: 600; font-size: 1rem; color: var(--cl-ink); margin-bottom: 0.2rem; }
.cl-optional { font-weight: 400; color: var(--cl-faint); }
.cl-privacy { font-size: 0.82rem; color: var(--cl-muted); text-align: center; margin-top: 0.6rem; }

/* Document preview: always a white "sheet of paper", in light and dark mode, like the downloaded file.
   Template values arrive as CSS variables from document_builder. */
.cl-doc { background: #fff; border: 1px solid var(--cl-border); border-radius: 10px; padding: 2.2rem 2.5rem;
          box-shadow: 0 1px 3px rgba(15,23,42,.05), 0 10px 30px rgba(15,23,42,.06); color-scheme: light;
          color: #111827; font-size: var(--doc-size, 0.9rem); line-height: 1.5; max-height: 1000px; overflow-y: auto; }
.cl-doc, .cl-doc * { font-family: var(--doc-font, Inter, sans-serif) !important; color: #111827; }
.cl-doc p { margin: 0.12rem 0 !important; font-size: var(--doc-size, 0.9rem) !important; }
.cl-doc ul { margin: 0.15rem 0 0.35rem 1.1rem !important; padding: 0 !important; }
.cl-doc li { margin: 0.08rem 0 !important; font-size: var(--doc-size, 0.9rem) !important; }
.cl-doc .cl-name { text-align: var(--doc-align, center); font-size: 1.6rem; font-weight: 700; color: var(--doc-accent, #1E3A8A); letter-spacing: -0.01em; }
.cl-doc .cl-contact { text-align: var(--doc-align, center); color: #64748B; font-size: 0.8rem; margin-top: 0.15rem; }
.cl-doc .cl-heading { margin: 1.1rem 0 0.45rem 0; color: var(--doc-accent, #1E3A8A); font-weight: 700; font-size: 0.8rem; letter-spacing: 0.08em; }
.cl-heading-rule { padding-bottom: 0.2rem; border-bottom: 1.5px solid var(--doc-accent, #1E3A8A); }
.cl-heading-bar { padding-left: 0.55rem; border-left: 3px solid var(--doc-accent, #1E3A8A); }
.cl-entry { font-weight: 600; margin-top: 0.55rem; }
[data-testid="stMetricValue"] { font-size: 1.9rem; }
.cl-letter { padding: 2.6rem 3rem; }
.cl-letter p { margin: 0 0 0.9rem 0 !important; }

.cl-chips { display: flex; flex-wrap: wrap; gap: 0.4rem; margin: 0.4rem 0 1rem 0; }
.cl-chip { font-size: 0.8rem; font-weight: 500; color: var(--cl-chip); background: var(--cl-chip-bg); border: 1px solid var(--cl-chip-line);
           border-radius: 999px; padding: 0.2rem 0.65rem; }
.cl-chip-good { color: var(--cl-good); background: var(--cl-good-bg); border-color: var(--cl-good-line); }
.cl-hero-sm { padding: 0.2rem 0 1.4rem 0; }
.cl-hero-sm .cl-h1 { font-size: 2.1rem; }
.cl-footer-rule { border-top: 1px solid var(--cl-border); margin-top: 3rem; padding-top: 0.6rem; }
.cl-rank { display: inline-flex; align-items: center; justify-content: center; width: 26px; height: 26px; border-radius: 999px;
           background: var(--cl-accent-fill); color: #fff; font-weight: 700; font-size: 0.85rem; margin-right: 0.5rem; }
.cl-prose { max-width: 780px; color: var(--cl-body); line-height: 1.65; }
.cl-prose h3 { color: var(--cl-ink); margin-top: 1.6rem; }
/* Requirement checklist: status is always shown as a text label, never by color alone */
.cl-reqs { border: 1px solid var(--cl-border); border-radius: 12px; padding: 0.2rem 1rem; margin: 0.4rem 0 0.6rem 0; }
.cl-req { display: flex; gap: 0.8rem; padding: 0.75rem 0; border-bottom: 1px solid var(--cl-divider); }
.cl-req:last-child { border-bottom: none; }
.cl-status { flex: 0 0 4.8rem; text-align: center; font-size: 0.74rem; font-weight: 700; border-radius: 999px;
             padding: 0.18rem 0; height: fit-content; border: 1px solid; }
.cl-status-met { color: var(--cl-good); background: var(--cl-good-bg); border-color: var(--cl-good-line); }
.cl-status-partial { color: var(--cl-warn); background: var(--cl-warn-bg); border-color: var(--cl-warn-line); }
.cl-status-not_met { color: var(--cl-bad); background: var(--cl-bad-bg); border-color: var(--cl-bad-line); }
.cl-req-text { font-weight: 600; color: var(--cl-ink); }
.cl-req-meta { font-size: 0.78rem; color: var(--cl-muted); margin-top: 0.1rem; }
.cl-req-reason { font-size: 0.88rem; color: var(--cl-body); margin-top: 0.25rem; }
.cl-req-evidence { font-size: 0.84rem; color: var(--cl-muted); font-style: italic; margin-top: 0.2rem;
                   border-left: 2px solid var(--cl-border); padding-left: 0.55rem; }

/* Verdict card at the top of the results */
.cl-verdict { border: 1px solid var(--cl-border); border-left: 5px solid var(--cl-verdict-line, var(--cl-accent)); border-radius: 12px;
              padding: 1.1rem 1.3rem; margin: 0.6rem 0 1.1rem 0; background: var(--cl-surface); }
.cl-verdict-good { --cl-verdict-line: light-dark(#16A34A, #4ADE80); }
.cl-verdict-ok { --cl-verdict-line: light-dark(#2563EB, #8DA8F0); }
.cl-verdict-warn { --cl-verdict-line: light-dark(#D97706, #FBBF24); }
.cl-verdict-bad { --cl-verdict-line: light-dark(#DC2626, #F87171); }
.cl-verdict-head { display: flex; align-items: center; flex-wrap: wrap; gap: 0.6rem; }
.cl-band { font-size: 0.78rem; font-weight: 700; border-radius: 999px; padding: 0.2rem 0.7rem; border: 1px solid; }
.cl-band-good { color: var(--cl-good); background: var(--cl-good-bg); border-color: var(--cl-good-line); }
.cl-band-ok { color: var(--cl-accent); background: var(--cl-accent-soft); border-color: var(--cl-accent-line); }
.cl-band-warn { color: var(--cl-warn); background: var(--cl-warn-bg); border-color: var(--cl-warn-line); }
.cl-band-bad { color: var(--cl-bad); background: var(--cl-bad-bg); border-color: var(--cl-bad-line); }
.cl-verdict-title { font-size: 1.15rem; font-weight: 700; color: var(--cl-ink); }
.cl-verdict-text { color: var(--cl-body); margin-top: 0.35rem; line-height: 1.55; }
.cl-fixes-title { font-weight: 600; color: var(--cl-ink); margin-top: 0.8rem; font-size: 0.92rem; }
.cl-fixes { margin: 0.3rem 0 0 0; padding-left: 1.2rem; color: var(--cl-body); }
.cl-fixes li { margin: 0.2rem 0; }
.cl-fix-tag { font-size: 0.74rem; color: var(--cl-muted); }

/* Step tracker shown while generating */
.cl-steps { display: grid; grid-template-columns: repeat(5, 1fr); gap: 0.5rem; margin: 0.8rem 0 0.4rem 0; }
.cl-step { border: 1px solid var(--cl-border); border-radius: 10px; padding: 0.6rem 0.7rem; background: var(--cl-surface); }
.cl-step-num { display: inline-flex; align-items: center; justify-content: center; width: 22px; height: 22px; border-radius: 999px;
               font-size: 0.75rem; font-weight: 700; border: 1.5px solid var(--cl-faint); color: var(--cl-muted); }
.cl-step-label { font-weight: 600; font-size: 0.86rem; color: var(--cl-muted); margin-top: 0.35rem; }
.cl-step-state { font-size: 0.74rem; color: var(--cl-faint); }
.cl-step-active { border-color: var(--cl-accent); box-shadow: 0 0 0 1px var(--cl-accent); }
.cl-step-active .cl-step-num { border-color: var(--cl-accent); color: var(--cl-accent); }
.cl-step-active .cl-step-label { color: var(--cl-ink); }
.cl-step-active .cl-step-state { color: var(--cl-accent); }
.cl-step-done .cl-step-num { background: var(--cl-accent-fill); border-color: var(--cl-accent-fill); color: #fff; }
.cl-step-done .cl-step-label { color: var(--cl-ink); }
@media (max-width: 640px) { .cl-steps { grid-template-columns: 1fr; } }

/* Landing: before/after example */
.cl-compare { display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; margin: 0.6rem 0 0.4rem 0; }
@media (max-width: 640px) { .cl-compare { grid-template-columns: 1fr; } }
.cl-sample { border: 1px solid var(--cl-border); border-radius: 12px; padding: 1rem 1.15rem; background: var(--cl-surface); }
.cl-sample-label { font-size: 0.74rem; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase; color: var(--cl-muted); margin-bottom: 0.5rem; }
.cl-sample ul { margin: 0; padding-left: 1.1rem; color: var(--cl-body); }
.cl-sample li { margin: 0.35rem 0; line-height: 1.5; }
.cl-sample mark { background: var(--cl-accent-soft); color: var(--cl-accent); padding: 0 0.15rem; border-radius: 3px; }
.cl-sample-foot { margin-top: 0.7rem; font-size: 0.82rem; color: var(--cl-muted); }
</style>
"""


def apply_styles():
    st.markdown(CSS, unsafe_allow_html=True)

# ------------------------------------------------------------------
# Anonymous usage counters (owner analytics only — counts, never content)
# ------------------------------------------------------------------
COUNTER_NAMESPACE = "ai-resume-generator-demo"


def _bump(counter_key: str):
    try:
        requests.get(f"https://api.counterapi.dev/v1/{COUNTER_NAMESPACE}/{counter_key}/up", timeout=3)
    except Exception:
        pass


def increment_counter():
    _bump("resumes-generated")


def record_feedback(helpful: bool):
    _bump("feedback-helpful" if helpful else "feedback-not-helpful")

# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------
def extract_text_from_upload(uploaded_file):
    if uploaded_file is None:
        return None
    name = uploaded_file.name.lower()

    if name.endswith(".txt"):
        return uploaded_file.read().decode("utf-8", errors="ignore")

    if name.endswith(".pdf"):
        import pypdf
        reader = pypdf.PdfReader(uploaded_file)
        return "\n".join((page.extract_text() or "") for page in reader.pages)

    if name.endswith(".docx"):
        import docx
        document = docx.Document(uploaded_file)
        return "\n".join(p.text for p in document.paragraphs)

    return None


def file_stem(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", name).strip("_") or APP_NAME


def chips(keywords, extra_class=""):
    items = "".join(f'<span class="cl-chip {extra_class}">{html.escape(str(k))}</span>' for k in keywords)
    st.markdown(f'<div class="cl-chips">{items}</div>', unsafe_allow_html=True)


def busy_message(exc) -> str:
    when = "later today" if getattr(exc, "daily", False) else "in a few minutes"
    return (f"{APP_NAME} is very busy right now — our free AI capacity is used up for the moment. "
            f"Please try again {when}. This attempt didn't count toward your limit.")


def page_intro(eyebrow: str, title: str, lead: str):
    st.markdown(f'''<div class="cl-hero cl-hero-sm"><div class="cl-eyebrow">{eyebrow}</div>
<div class="cl-h1">{title}</div><div class="cl-lead">{lead}</div></div>''', unsafe_allow_html=True)


STATUS_LABELS = {"met": "Met", "partial": "Partial", "not_met": "Missing"}
CATEGORY_LABELS = {"experience_years": "Experience", "skill": "Skill", "knowledge": "Knowledge", "education": "Education",
                   "certification": "Certification", "title": "Job title", "soft_skill": "Soft skill"}


def requirement_checklist(items, before_items=None):
    """Recruiter-style checklist: gaps first (required before preferred), then what's already met."""
    before_status = {i["id"]: i["status"] for i in (before_items or [])}
    order = {"not_met": 0, "partial": 1, "met": 2}
    rows = []
    # Gaps first; within each status, the requirements that carry the most weight first.
    for item in sorted(items, key=lambda i: (order[i["status"]], -i.get("weight", 1))):
        meta = [item["importance"].title(), CATEGORY_LABELS.get(item["category"], "")]
        was = before_status.get(item["id"])
        if was and was != item["status"]:
            meta.append(f"was {STATUS_LABELS[was]} before tailoring")
        evidence = (f'<div class="cl-req-evidence">&ldquo;{html.escape(item["evidence"])}&rdquo;</div>'
                    if item.get("evidence") else "")
        reason = f'<div class="cl-req-reason">{html.escape(item["reason"])}</div>' if item.get("reason") else ""
        rows.append(
            f'<div class="cl-req"><div class="cl-status cl-status-{item["status"]}">{STATUS_LABELS[item["status"]]}</div>'
            f'<div><div class="cl-req-text">{html.escape(item["text"])}</div>'
            f'<div class="cl-req-meta">{" · ".join(html.escape(m) for m in meta if m)}</div>{reason}{evidence}</div></div>'
        )
    st.markdown(f'<div class="cl-reqs">{"".join(rows)}</div>', unsafe_allow_html=True)


# ------------------------------------------------------------------
# Theme (light / dark)
# ------------------------------------------------------------------
def is_dark_theme() -> bool:
    """The active theme, as reported by the browser. Falls back to light if it isn't known yet."""
    try:
        return st.context.theme.type == "dark"
    except Exception:
        return False


def chart_palette() -> dict:
    """Colors for Altair charts, which can't read CSS variables. Same hue in both themes, adjusted for contrast."""
    if is_dark_theme():
        return {"before": "#4C5F99", "after": "#8DA8F0", "text": "#CBD5E1", "muted": "#94A3B8",
                "grid": "#262D3B", "rule": "#475569", "ink": "#F1F5F9", "point_stroke": "#0E1117"}
    return {"before": "#94A8D8", "after": "#1E3A8A", "text": "#334155", "muted": "#64748B",
            "grid": "#EEF1F5", "rule": "#CBD5E1", "ink": "#0F172A", "point_stroke": "#FFFFFF"}

# ------------------------------------------------------------------
# Verdict card: what the scores mean, in plain words
# ------------------------------------------------------------------
# (minimum score, band label, card tone, explanation). Our scoring is strict on purpose, so the bands are
# calibrated to it: 65+ is already a good, competitive match.
SCORE_BANDS = [
    (80, "Strong match", "good", "You meet nearly everything this job asks for. Apply with confidence."),
    (65, "Good match", "ok", "You cover most of what this job asks for. Closing a gap or two would make "
                             "your application even stronger."),
    (45, "Fair match", "warn", "You meet the core of the role, but there are clear gaps. Address the top fixes "
                               "below (in your resume or cover letter) before applying."),
    (0, "Stretch role", "bad", "This job asks for a lot that your resume doesn't show yet. Apply if you have "
                               "relevant experience that isn't on your resume; otherwise focus on closer-fit roles."),
]


def score_band(score) -> tuple[str, str, str]:
    """(label, tone, explanation) for a 0–100 score."""
    for minimum, label, tone, text in SCORE_BANDS:
        if score >= minimum:
            return label, tone, text
    return SCORE_BANDS[-1][1:]


def top_fixes(items, limit=3):
    """The most valuable gaps to close: required before preferred, missing before partial, heaviest first."""
    gaps = [i for i in items if i["status"] != "met" and i.get("category") != "soft_skill"]
    order = {"not_met": 0, "partial": 1}
    importance = {"required": 0, "preferred": 1}
    gaps.sort(key=lambda i: (importance.get(i.get("importance"), 2), order[i["status"]], -i.get("weight", 1)))
    return gaps[:limit]


def verdict_card(requirement_score, items, ats_score, has_job, stale=False):
    """The summary at the top of the results: a score band, a one-line verdict, and the top things to fix."""
    if not has_job or requirement_score is None:
        label, tone, _ = score_band(ats_score)
        title = "Your resume is polished and ready"
        text = ("Add a job description and generate again to see how well you match a specific job, "
                "which requirements you meet, and what to fix first.")
        fixes_html = ""
        band_html = ""
    else:
        label, tone, text = score_band(requirement_score)
        met = sum(i["status"] == "met" for i in items)
        partial = sum(i["status"] == "partial" for i in items)
        title = f"You meet {met} of {len(items)} requirements" + (f", and {partial} partly" if partial else "")
        band_html = f'<span class="cl-band cl-band-{tone}">{label} &middot; {requirement_score}/100</span>'
        fixes = top_fixes(items)
        if fixes:
            rows = "".join(
                f'<li>{html.escape(i["text"])} <span class="cl-fix-tag">&middot; '
                f'{STATUS_LABELS[i["status"]]}, {html.escape(i.get("importance", "").lower())}</span></li>'
                for i in fixes)
            heading = "What to address" if len(fixes) == 1 else f"Top {len(fixes)} to address"
            fixes_html = (f'<div class="cl-fixes-title">{heading}</div><ol class="cl-fixes">{rows}</ol>'
                          '<div class="cl-fix-tag" style="margin-top:0.4rem">Only add what you genuinely have. '
                          'Otherwise, address the gap in your cover letter.</div>')
        else:
            fixes_html = '<div class="cl-fixes-title">No gaps found. Every requirement is covered.</div>'
        if stale:
            text += " (Based on the last requirement check. Re-check in Job match after editing.)"
    st.markdown(
        f'<div class="cl-verdict cl-verdict-{tone}"><div class="cl-verdict-head">{band_html}'
        f'<span class="cl-verdict-title">{html.escape(title)}</span></div>'
        f'<div class="cl-verdict-text">{html.escape(text)}</div>{fixes_html}</div>',
        unsafe_allow_html=True,
    )

# ------------------------------------------------------------------
# Step tracker while generating
# ------------------------------------------------------------------
PROGRESS_STAGES = ["Reading", "Matching", "Writing", "Checking", "Finishing"]
# Progress messages from main.orchestrator -> the stage they belong to (matched by their opening words).
_STAGE_BY_MESSAGE = [
    ("Reading", 0), ("Matching", 1), ("Analyzing", 1), ("Writing", 2), ("Polishing", 2),
    ("Checking", 3), ("Removing", 3), ("Reviewing", 4), ("Finishing", 4),
]


def progress_stage(message: str, current: int = 0) -> int:
    """Which stage a progress message belongs to. Never moves backwards; unknown messages keep the current stage."""
    for prefix, stage in _STAGE_BY_MESSAGE:
        if message.startswith(prefix):
            return max(stage, current)
    return current


def step_tracker_html(active: int, done: bool = False) -> str:
    cells = []
    for i, label in enumerate(PROGRESS_STAGES):
        if done or i < active:
            cls, state, mark = "cl-step-done", "Done", "&#10003;"
        elif i == active:
            cls, state, mark = "cl-step-active", "In progress", str(i + 1)
        else:
            cls, state, mark = "", "Waiting", str(i + 1)
        cells.append(f'<div class="cl-step {cls}"><span class="cl-step-num">{mark}</span>'
                     f'<div class="cl-step-label">{label}</div><div class="cl-step-state">{state}</div></div>')
    return f'<div class="cl-steps">{"".join(cells)}</div>'

# ------------------------------------------------------------------
# Upload check: catch unreadable PDFs before spending AI calls on them
# ------------------------------------------------------------------
SECTION_WORDS = ("experience", "education", "skills", "employment", "work history", "projects", "summary")


def text_quality_issues(text: str) -> list[str]:
    """Plain-language problems with text extracted from an uploaded resume (empty list = looks fine)."""
    issues = []
    stripped = (text or "").strip()
    if len(stripped) < 400:
        issues.append(f"We found only {len(stripped):,} characters of text. If your resume is longer, the file may be "
                      "a scanned image. Upload a DOCX, or paste the text instead.")
    garbled = stripped.count("�") + stripped.count("(cid:") + len(re.findall(r"[-]", stripped))
    if garbled >= 5:
        issues.append("Some characters didn't come through correctly (the PDF uses unusual fonts or symbols).")
    if len(re.findall(r"(?:\b\w ){4,}\w\b", stripped)) >= 3:
        issues.append("Some words came out with spaces between the letters (like “P y t h o n”), which AI and "
                      "applicant tracking systems can't read.")
    lines = [line for line in stripped.splitlines() if line.strip()]
    if len(lines) >= 25 and sum(len(line.split()) <= 2 for line in lines) / len(lines) > 0.6:
        issues.append("The text is broken into many short fragments. This is common with two-column or table "
                      "layouts, and can scramble the order of your experience.")
    if len(stripped) >= 400 and not any(word in stripped.lower() for word in SECTION_WORDS):
        issues.append("We couldn't find standard sections such as Experience, Education, or Skills.")
    return issues
