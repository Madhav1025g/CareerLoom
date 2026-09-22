import html
import os
import re
import uuid
from datetime import date

import requests
import streamlit as st

# ------------------------------------------------------------------
# Load secrets (API keys) from Streamlit Cloud's secrets manager.
# Locally there may be no secrets.toml — main.py falls back to .env.
# ------------------------------------------------------------------
try:
    for key in ["OPENAI_API_KEY", "GROQ_API_KEY", "QDRANT_URL", "QDRANT_API_KEY", "LLM_PROVIDER", "API_KEY_HERE"]:
        if key in st.secrets:
            os.environ[key] = st.secrets[key]
except Exception:
    pass

import altair as alt
import pandas as pd

from main import APP_NAME, PIPELINE_STEPS, LLMUnavailableError, ResumeGenerationError, log_event, orchestrator
from document_builder import (
    DEFAULT_TEMPLATE,
    TEMPLATES,
    build_letter_docx,
    build_letter_pdf,
    build_resume_docx,
    build_resume_pdf,
    letter_to_html,
    resume_to_html,
)

# ------------------------------------------------------------------
# Page setup + styling
# ------------------------------------------------------------------
st.set_page_config(
    page_title=f"{APP_NAME} | AI Resume & Cover Letter Builder",
    page_icon="assets/favicon.png",
    layout="wide",
)

st.markdown("""
<style>
.block-container { max-width: 1140px; padding-top: 2.2rem; padding-bottom: 3rem; }
header[data-testid="stHeader"] { background: transparent; }

.cl-nav { display: flex; align-items: center; justify-content: space-between; margin-bottom: 2.4rem; }
.cl-brand { display: flex; align-items: center; gap: 0.6rem; font-weight: 700; font-size: 1.25rem; color: #0F172A; letter-spacing: -0.01em; }
.cl-mark { display: inline-flex; align-items: center; justify-content: center; width: 34px; height: 34px;
           border-radius: 8px; background: #1E3A8A; color: #fff; font-size: 0.85rem; font-weight: 700; }
.cl-mark span { color: #F59E0B; }
.cl-pill { font-size: 0.78rem; font-weight: 600; color: #1E3A8A; background: #EEF2FF; border: 1px solid #DCE3F9;
           padding: 0.3rem 0.75rem; border-radius: 999px; }

.cl-hero { padding: 0.5rem 0 1.8rem 0; max-width: 780px; }
.cl-eyebrow { text-transform: uppercase; letter-spacing: 0.12em; font-size: 0.75rem; font-weight: 700; color: #B45309; margin-bottom: 0.7rem; }
.cl-h1 { font-size: 2.6rem; line-height: 1.12; font-weight: 700; color: #0F172A; letter-spacing: -0.025em; margin-bottom: 0.9rem; }
.cl-lead { font-size: 1.08rem; line-height: 1.6; color: #475569; }

.cl-features { display: grid; grid-template-columns: repeat(auto-fit, minmax(230px, 1fr)); gap: 1rem; margin-bottom: 2.6rem; }
.cl-feature { border: 1px solid #E3E7EF; border-radius: 12px; padding: 1.1rem 1.2rem; background: #FAFBFD; }
.cl-feature-title { font-weight: 600; color: #0F172A; margin-bottom: 0.3rem; }
.cl-feature-text { font-size: 0.9rem; color: #64748B; line-height: 1.5; }

.cl-section-title { font-size: 1.45rem; font-weight: 700; color: #0F172A; letter-spacing: -0.015em; margin: 0.4rem 0 0.2rem 0; }
.cl-section-sub { color: #64748B; font-size: 0.95rem; margin-bottom: 1rem; }
.cl-card-title { font-weight: 600; font-size: 1rem; color: #0F172A; margin-bottom: 0.2rem; }
.cl-privacy { font-size: 0.82rem; color: #64748B; text-align: center; margin-top: 0.6rem; }

/* Document preview — template values arrive as CSS variables from document_builder */
.cl-doc { background: #fff; border: 1px solid #E3E7EF; border-radius: 10px; padding: 2.2rem 2.5rem;
          box-shadow: 0 1px 3px rgba(15,23,42,.05), 0 10px 30px rgba(15,23,42,.06);
          color: #111827; font-size: var(--doc-size, 0.9rem); line-height: 1.5; max-height: 1000px; overflow-y: auto; }
.cl-doc, .cl-doc * { font-family: var(--doc-font, Inter, sans-serif) !important; }
.cl-doc p { margin: 0.12rem 0 !important; font-size: var(--doc-size, 0.9rem) !important; }
.cl-doc ul { margin: 0.15rem 0 0.35rem 1.1rem !important; padding: 0 !important; }
.cl-doc li { margin: 0.08rem 0 !important; font-size: var(--doc-size, 0.9rem) !important; }
.cl-name { text-align: var(--doc-align, center); font-size: 1.6rem; font-weight: 700; color: var(--doc-accent, #1E3A8A); letter-spacing: -0.01em; }
.cl-contact { text-align: var(--doc-align, center); color: #64748B; font-size: 0.8rem; margin-top: 0.15rem; }
.cl-heading { margin: 1.1rem 0 0.45rem 0; color: var(--doc-accent, #1E3A8A); font-weight: 700; font-size: 0.8rem; letter-spacing: 0.08em; }
.cl-heading-rule { padding-bottom: 0.2rem; border-bottom: 1.5px solid var(--doc-accent, #1E3A8A); }
.cl-heading-bar { padding-left: 0.55rem; border-left: 3px solid var(--doc-accent, #1E3A8A); }
.cl-entry { font-weight: 600; margin-top: 0.55rem; }
[data-testid="stMetricValue"] { font-size: 1.9rem; }
.cl-letter { padding: 2.6rem 3rem; }
.cl-letter p { margin: 0 0 0.9rem 0 !important; }

.cl-chips { display: flex; flex-wrap: wrap; gap: 0.4rem; margin: 0.4rem 0 1rem 0; }
.cl-chip { font-size: 0.8rem; font-weight: 500; color: #9A3412; background: #FFF7ED; border: 1px solid #FED7AA;
           border-radius: 999px; padding: 0.2rem 0.65rem; }

.cl-footer { border-top: 1px solid #E3E7EF; margin-top: 3rem; padding-top: 1.2rem; color: #94A3B8; font-size: 0.82rem;
             display: flex; justify-content: space-between; flex-wrap: wrap; gap: 0.5rem; }
</style>
""", unsafe_allow_html=True)

# ------------------------------------------------------------------
# Header + hero
# ------------------------------------------------------------------
st.markdown(f"""
<div class="cl-nav">
  <div class="cl-brand"><span class="cl-mark">C<span>L</span></span>{APP_NAME}</div>
  <div class="cl-pill">Free &middot; No sign-up required</div>
</div>
<div class="cl-hero">
  <div class="cl-eyebrow">AI career document platform</div>
  <div class="cl-h1">Tailor your resume to every job you apply for.</div>
  <div class="cl-lead">{APP_NAME} reads your resume and the job description, rewrites your resume for the role,
  shows how much your ATS score improved, and adds a 15-second recruiter snapshot and a matching cover letter &mdash;
  in under a minute.</div>
</div>
<div class="cl-features">
  <div class="cl-feature">
    <div class="cl-feature-title">ATS score, before and after</div>
    <div class="cl-feature-text">Semantic and keyword matching show how well you fit the role, what's missing, and how much tailoring helped.</div>
  </div>
  <div class="cl-feature">
    <div class="cl-feature-title">Resume, snapshot &amp; cover letter</div>
    <div class="cl-feature-text">An {len(PIPELINE_STEPS)}-step AI pipeline tailors your resume without dropping experience, plus a half-page recruiter snapshot.</div>
  </div>
  <div class="cl-feature">
    <div class="cl-feature-title">Recruiter-ready exports</div>
    <div class="cl-feature-text">Edit on the page, pick one of {len(TEMPLATES)} professional templates, and download PDF or Word.</div>
  </div>
</div>
""", unsafe_allow_html=True)

# ------------------------------------------------------------------
# Usage counter (owner analytics only — not shown on the page)
# ------------------------------------------------------------------
COUNTER_NAMESPACE = "ai-resume-generator-demo"
COUNTER_KEY = "resumes-generated"


def increment_counter():
    try:
        requests.get(f"https://api.counterapi.dev/v1/{COUNTER_NAMESPACE}/{COUNTER_KEY}/up", timeout=3)
    except Exception:
        pass

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


SAMPLE_RESUME = """Jordan Lee
Software Engineer
jordan.lee@email.com | (555) 123-4567 | Boston, MA

PROFESSIONAL SUMMARY
Backend Software Engineer with 5 years of experience building REST APIs and cloud-native
applications. Strong background in Python, FastAPI, and AWS.

EXPERIENCE
TechCorp Inc. — Remote | Jan 2021 - Present
Software Engineer
- Built and maintained REST APIs serving 1M+ daily requests using Python and FastAPI
- Deployed microservices on AWS Lambda and ECS, reducing infra costs by 20%
- Automated CI/CD pipelines using GitHub Actions and Docker

SKILLS
Python, FastAPI, AWS, Docker, PostgreSQL, REST APIs, Git
"""

SAMPLE_JD = """We are hiring a Backend Software Engineer with experience in Python, FastAPI, and AWS.
The ideal candidate has built and scaled REST APIs, has experience with Docker and CI/CD,
and is comfortable working in an Agile team environment.
"""

# ------------------------------------------------------------------
# Session state
# ------------------------------------------------------------------
if "full_name" not in st.session_state:
    st.session_state.full_name = ""
    st.session_state.current_role = ""
    st.session_state.skills_input = ""
    st.session_state.experience_years = 0
    st.session_state.resume_text_area = ""
    st.session_state.job_description_area = ""

MAX_GENERATIONS_PER_SESSION = 3
if "generation_count" not in st.session_state:
    st.session_state.generation_count = 0

# ------------------------------------------------------------------
# Input section
# ------------------------------------------------------------------
title_col, sample_col = st.columns([4, 1], vertical_alignment="bottom")
with title_col:
    st.markdown('<div class="cl-section-title">Build your application</div>'
                '<div class="cl-section-sub">Add your details and resume. A job description unlocks ATS matching and a tailored cover letter.</div>',
                unsafe_allow_html=True)
with sample_col:
    if st.button("Load example", width="stretch"):
        st.session_state.full_name = "Jordan Lee"
        st.session_state.current_role = "Software Engineer"
        st.session_state.skills_input = "Python, FastAPI, AWS, Docker, PostgreSQL, REST APIs, Git"
        st.session_state.experience_years = 5
        st.session_state.resume_text_area = SAMPLE_RESUME
        st.session_state.job_description_area = SAMPLE_JD
        st.rerun()

left, right = st.columns(2, gap="large")

with left:
    with st.container(border=True):
        st.markdown('<div class="cl-card-title">Your profile</div>', unsafe_allow_html=True)
        col1, col2 = st.columns(2)
        with col1:
            full_name = st.text_input("Full name", key="full_name")
            experience_years = st.number_input("Years of experience", min_value=0, max_value=50, step=1, key="experience_years")
        with col2:
            current_role = st.text_input("Current role", placeholder="e.g. Software Engineer", key="current_role")
            skills_input = st.text_input("Key skills (comma-separated)", placeholder="Python, FastAPI, AWS", key="skills_input")

    with st.container(border=True):
        st.markdown('<div class="cl-card-title">Your resume</div>', unsafe_allow_html=True)
        input_mode = st.segmented_control(
            "Resume input", ["Upload a file", "Paste text"], default="Upload a file", label_visibility="collapsed",
        ) or "Upload a file"

        resume_text = None
        if input_mode == "Upload a file":
            uploaded_file = st.file_uploader("Upload your resume (PDF, DOCX, or TXT)", type=["pdf", "docx", "txt"])
            if uploaded_file is not None:
                resume_text = extract_text_from_upload(uploaded_file)
                if resume_text:
                    st.success(f"Loaded {uploaded_file.name} ({len(resume_text):,} characters)")
                else:
                    st.error("We couldn't read that file. Try a DOCX or TXT version instead.")
            elif st.session_state.resume_text_area:
                resume_text = st.session_state.resume_text_area
                st.info("Using the example resume. Switch to “Paste text” to view or edit it.")
        else:
            resume_text = st.text_area("Paste your resume", height=240, key="resume_text_area")

with right:
    with st.container(border=True):
        st.markdown('<div class="cl-card-title">Target job <span style="font-weight:400;color:#94A3B8">(recommended)</span></div>',
                    unsafe_allow_html=True)
        job_description = st.text_area(
            "Job description",
            height=372,
            key="job_description_area",
            placeholder="Paste the full job description here...",
        )

remaining = MAX_GENERATIONS_PER_SESSION - st.session_state.generation_count
if remaining <= 0:
    st.warning(
        f"You've reached the limit of {MAX_GENERATIONS_PER_SESSION} generations for this session. "
        "This keeps the service free for everyone — please come back later."
    )
    generate_clicked = False
else:
    generate_clicked = st.button("Generate my application", type="primary", width="stretch")

st.markdown(
    f'<div class="cl-privacy">Your resume is sent to our AI provider only to generate your results. '
    f'{APP_NAME} does not store it.</div>',
    unsafe_allow_html=True,
)

# ------------------------------------------------------------------
# Run pipeline with live progress
# ------------------------------------------------------------------
if generate_clicked:
    if not full_name or not resume_text:
        st.error("Please add at least your name and your resume.")
    else:
        user_request = {
            "full_name": full_name,
            "current_role": current_role,
            "skills": [s.strip() for s in skills_input.split(",") if s.strip()],
            "experience_years": int(experience_years),
            "resume_text": resume_text,
            "resume_file": None,
            "job_description": job_description or None,
        }
        request_id = str(uuid.uuid4())

        result = None
        with st.status("Generating your application...", expanded=True) as status:
            def update(msg):
                status.update(label=msg)
                st.write(msg)

            try:
                result = orchestrator(user_request, request_id, progress_callback=update)
                status.update(label="Your application is ready", state="complete", expanded=False)
            except LLMUnavailableError:
                status.update(label="Generation failed", state="error")
                st.error("Our AI service is temporarily unavailable. Please try again in a minute.")
            except ResumeGenerationError:
                status.update(label="Generation failed", state="error")
                st.error("We couldn't generate a complete resume this time. This occasionally happens with long "
                         "resumes — please try again. This attempt didn't count toward your limit.")
            except Exception as exc:
                log_event(f"{request_id}: unexpected error ({type(exc).__name__})")
                status.update(label="Generation failed", state="error")
                st.error("Something went wrong while generating your application. Please try again.")

        if result is not None:
            increment_counter()
            st.session_state.generation_count += 1

            workflow = result["workflow"]
            # Documents live in session state so edits and Apply-fix buttons persist across reruns.
            st.session_state.originals = {
                "resume": workflow["human_optimizer"]["human_friendly_resume"],
                "snapshot": workflow["recruiter_snapshot"]["snapshot"],
                "cover_letter": workflow["cover_letter"]["cover_letter"],
            }
            st.session_state.docs = dict(st.session_state.originals)
            st.session_state.doc_versions = {key: 0 for key in st.session_state.docs}
            st.session_state.last_result = result
            st.session_state.last_full_name = full_name

# ------------------------------------------------------------------
# Results helpers
# ------------------------------------------------------------------
def set_document(doc_key: str, text: str):
    """Replace a document's text and refresh its editor (editor widgets are keyed by version)."""
    st.session_state.docs[doc_key] = text
    st.session_state.doc_versions[doc_key] += 1


def save_edit(doc_key: str, widget_key: str):
    st.session_state.docs[doc_key] = st.session_state[widget_key]


def document_panel(doc_key: str, noun: str, file_label: str, template: str, stem: str, full_name: str,
                   below_downloads=None):
    """Preview/edit toggle on the left; downloads, reset, and optional extras (below_downloads) on the right."""
    text = st.session_state.docs[doc_key]
    is_letter = doc_key == "cover_letter"
    doc_col, action_col = st.columns([3, 1], gap="large")

    with doc_col:
        mode = st.segmented_control(
            f"{noun} view", ["Preview", "Edit"], default="Preview", key=f"mode_{doc_key}", label_visibility="collapsed",
        ) or "Preview"
        if mode == "Edit":
            widget_key = f"editor_{doc_key}_{st.session_state.doc_versions[doc_key]}"
            st.text_area(
                f"Edit your {noun}", value=text, height=640, key=widget_key,
                on_change=save_edit, args=(doc_key, widget_key), label_visibility="collapsed",
            )
            st.caption("Edits save when you click outside the box. Keep section titles in CAPITALS and start "
                       "bullets with “- ” so the PDF and Word files format correctly.")
        elif is_letter:
            st.markdown(letter_to_html(text, template), unsafe_allow_html=True)
        else:
            st.markdown(resume_to_html(text, template), unsafe_allow_html=True)

    with action_col:
        st.markdown('<div class="cl-card-title">Download</div>', unsafe_allow_html=True)
        pdf = build_letter_pdf(text, full_name, template) if is_letter else build_resume_pdf(text, template)
        docx_bytes = build_letter_docx(text, full_name, template) if is_letter else build_resume_docx(text, template)
        st.download_button("PDF", data=pdf, file_name=f"{stem}_{file_label}.pdf", mime="application/pdf",
                           type="primary", width="stretch", key=f"pdf_{doc_key}")
        st.download_button("Word (DOCX)", data=docx_bytes, file_name=f"{stem}_{file_label}.docx",
                           mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                           width="stretch", key=f"docx_{doc_key}")
        st.download_button("Plain text", data=text, file_name=f"{stem}_{file_label}.txt", mime="text/plain",
                           width="stretch", key=f"txt_{doc_key}")
        st.divider()
        if text != st.session_state.originals[doc_key]:
            if st.button("Undo all edits", width="stretch", key=f"reset_{doc_key}"):
                set_document(doc_key, st.session_state.originals[doc_key])
                st.rerun()
        if below_downloads:
            below_downloads()


# Score changes this small are within the scorer's normal variation — don't present them as a gain or loss.
SCORE_NOISE = 2


def change_label(change: int) -> str:
    return "About the same as original" if abs(change) <= SCORE_NOISE else f"{change:+d} vs. original"


def score_rows(before: dict, after: dict, short: bool = False) -> list[tuple[str, int, int]]:
    names = ("Overall", "Keyword", "Semantic") if short else ("Overall ATS score", "Keyword match", "Semantic match")
    rows = [(names[0], before["ats_score"], after["ats_score"]),
            (names[1], before["keyword_score"], after["keyword_score"])]
    if before.get("semantic_score") is not None and after.get("semantic_score") is not None:
        rows.append((names[2], before["semantic_score"], after["semantic_score"]))
    return rows


def ats_bar_chart(before: dict, after: dict):
    """Compact grouped bars (original vs. tailored) sized for the narrow download column."""
    rows = score_rows(before, after, short=True)
    long = pd.DataFrame(
        [(m, version, score, f"{a - b:+d}") for m, b, a in rows for version, score in (("Original", b), ("Tailored", a))],
        columns=["Measure", "Version", "Score", "Change"],
    )
    order = [m for m, _, _ in rows]
    encoding = dict(
        y=alt.Y("Measure:N", sort=order, title=None, scale=alt.Scale(paddingInner=0.3),
                axis=alt.Axis(ticks=False, domain=False, labelColor="#334155", labelFontSize=12, labelPadding=6)),
        yOffset=alt.YOffset("Version:N", sort=["Original", "Tailored"], scale=alt.Scale(paddingInner=0.12)),
        # Extra room past 100 keeps the value labels at the bar tips inside the chart.
        x=alt.X("Score:Q", title=None, scale=alt.Scale(domain=[0, 118]),
                axis=alt.Axis(values=[0, 50, 100], gridColor="#EEF1F5", domain=False, ticks=False, labelColor="#64748B")),
    )
    bars = alt.Chart(long).mark_bar(cornerRadiusEnd=4).encode(
        **encoding,
        color=alt.Color("Version:N", scale=alt.Scale(domain=["Original", "Tailored"], range=["#94A8D8", "#1E3A8A"]),
                        legend=alt.Legend(title=None, orient="top", direction="horizontal", labelFontSize=11,
                                          labelColor="#334155", symbolType="square", symbolSize=90)),
        tooltip=[alt.Tooltip("Measure:N"), alt.Tooltip("Version:N", title="Resume"), alt.Tooltip("Score:Q"),
                 alt.Tooltip("Change:N", title="Change after tailoring")],
    )
    labels = alt.Chart(long).mark_text(align="left", dx=4, fontSize=11, color="#334155").encode(
        **encoding, text="Score:Q",
    )
    # Size by step (each bar 16px) so bars stay readable whatever the column width; "fit" + padding keeps
    # the measure names from being clipped on narrow screens.
    return (
        (bars + labels)
        .properties(height=alt.Step(16), padding={"left": 8, "right": 4, "top": 4, "bottom": 4},
                    autosize=alt.AutoSizeParams(type="fit-x", contains="padding"))
        .configure_view(strokeWidth=0)
    )


def ats_dumbbell_chart(before: dict, after: dict):
    """Before -> after per measure: one hue, two shades, joined by a neutral rule (a dumbbell chart)."""
    rows = score_rows(before, after)

    wide = pd.DataFrame(rows, columns=["Measure", "Original", "Tailored"])
    wide["Change"] = (wide["Tailored"] - wide["Original"]).map(lambda d: f"{d:+d}")
    wide["Label"] = wide["Tailored"].astype(str) + " (" + wide["Change"] + ")"
    long = wide.melt(id_vars=["Measure", "Change"], value_vars=["Original", "Tailored"],
                     var_name="Version", value_name="Score")

    order = list(wide["Measure"])
    y = alt.Y("Measure:N", sort=order, title=None,
              axis=alt.Axis(labelFontSize=13, labelColor="#334155", ticks=False, domain=False, labelPadding=12, labelLimit=220))
    x_scale = alt.Scale(domain=[0, 100])
    x_axis = alt.Axis(values=[0, 25, 50, 75, 100], gridColor="#EEF1F5", domain=False, ticks=False,
                      labelColor="#64748B", titleColor="#64748B", titleFontWeight="normal")

    rule = alt.Chart(wide).mark_rule(color="#CBD5E1", strokeWidth=2).encode(
        y=y, x=alt.X("Original:Q", scale=x_scale, axis=x_axis, title="Score (0–100)"), x2="Tailored:Q",
    )
    points = alt.Chart(long).mark_circle(size=190, opacity=1, stroke="white", strokeWidth=2).encode(
        y=y,
        x=alt.X("Score:Q", scale=x_scale),
        color=alt.Color("Version:N", scale=alt.Scale(domain=["Original", "Tailored"], range=["#94A8D8", "#1E3A8A"]),
                        legend=alt.Legend(title=None, orient="top", direction="horizontal", labelFontSize=12,
                                          labelColor="#334155", symbolSize=140, symbolStrokeWidth=0)),
        tooltip=[alt.Tooltip("Measure:N"), alt.Tooltip("Version:N", title="Resume"),
                 alt.Tooltip("Score:Q"), alt.Tooltip("Change:N", title="Change after tailoring")],
    )
    # Selective direct label: only the tailored endpoint, with the change.
    labels = alt.Chart(wide).mark_text(dy=-17, fontSize=12, fontWeight=600, color="#0F172A").encode(
        y=y, x=alt.X("Tailored:Q", scale=x_scale), text="Label:N",
    )
    chart = (rule + points + labels).properties(height=78 * len(rows) + 40)
    return chart.configure_view(strokeWidth=0), wide[["Measure", "Original", "Tailored", "Change"]]

# ------------------------------------------------------------------
# Results (persist across reruns via session_state, so Apply buttons work)
# ------------------------------------------------------------------
if "last_result" in st.session_state and "docs" in st.session_state:
    result = st.session_state.last_result
    workflow = result["workflow"]
    full_name = st.session_state.last_full_name
    stem = file_stem(full_name)

    ats_data = workflow["ats_optimization"]
    before = ats_data.get("before", {"ats_score": ats_data.get("ats_score", 0),
                                     "keyword_score": ats_data.get("keyword_score", 0),
                                     "semantic_score": ats_data.get("semantic_score")})
    after = ats_data.get("after", before)
    completeness = workflow.get("completeness_check", {})
    suggestions = workflow["reviewer"].get("suggestions", [])
    analyzer = workflow.get("analyzer", {}) if isinstance(workflow.get("analyzer"), dict) else {}

    st.write("")
    st.markdown(f'<div class="cl-section-title">Your results</div>'
                f'<div class="cl-section-sub">Generated in {result["execution_time"]} seconds.</div>',
                unsafe_allow_html=True)

    change = after["ats_score"] - before["ats_score"]
    m1, m2, m3, m4 = st.columns(4)
    meaningful = abs(change) > SCORE_NOISE
    m1.metric("ATS match", f"{after['ats_score']}/100", delta=change_label(change),
              delta_color="normal" if meaningful else "off", delta_arrow="auto" if meaningful else "off", border=True)
    m2.metric("Experience preserved", f"{completeness.get('completeness_pct', 100)}%", border=True)
    m3.metric("Review suggestions", len(suggestions), border=True)
    m4.metric("Candidate level", analyzer.get("candidate_level") or "—", border=True)

    style_col, style_note_col = st.columns([2, 3], vertical_alignment="center")
    with style_col:
        template = st.segmented_control(
            "Document style", list(TEMPLATES), default=DEFAULT_TEMPLATE, key="template",
        ) or DEFAULT_TEMPLATE
    with style_note_col:
        st.caption(TEMPLATES[template]["description"] + " Applies to the preview and every download.")

    tab_resume, tab_snapshot, tab_letter, tab_ats, tab_review, tab_draft = st.tabs(
        ["Tailored resume", "Recruiter snapshot", "Cover letter", "ATS analysis", "Review suggestions", "First draft"]
    )

    with tab_resume:
        if completeness.get("possibly_missing"):
            st.warning(
                f"Content check: {completeness['completeness_pct']}% of the entries we detected in your original "
                "resume appear in this version. Please double-check these lines weren't dropped:"
            )
            for line in completeness["possibly_missing"]:
                st.caption(f"• {line}")
        def resume_score_chart():
            st.markdown('<div class="cl-card-title">ATS score</div>', unsafe_allow_html=True)
            st.caption(f"Original vs. tailored · {change_label(change).lower()}")
            st.altair_chart(ats_bar_chart(before, after), width="stretch")
            if workflow["human_optimizer"].get("fallback_reason") == "lower ATS score":
                st.caption("We kept the first draft because it scored higher than the polished version.")

        document_panel("resume", "resume", "Resume", template, stem, full_name, below_downloads=resume_score_chart)

    with tab_snapshot:
        st.caption("A half-page version a recruiter can scan in 10–15 seconds. Send it alongside your full "
                   "resume, or paste it into a message to a recruiter.")
        document_panel("snapshot", "recruiter snapshot", "Recruiter_Snapshot", template, stem, full_name)

    with tab_letter:
        document_panel("cover_letter", "cover letter", "Cover_Letter", template, stem, full_name)

    with tab_ats:
        chart, table = ats_dumbbell_chart(before, after)
        overall_note = "about the same overall" if not meaningful else f"{change:+d} points overall"
        st.markdown(f"**ATS score: original vs. tailored resume** &nbsp;·&nbsp; {overall_note}")
        st.altair_chart(chart, width="stretch")
        st.caption("Both versions are scored the same way. Keyword match uses the skills you entered; "
                   "semantic match compares your resume to the job description.")
        with st.expander("View as table"):
            st.dataframe(table, hide_index=True, width="stretch")

        st.write("")
        explanation = ats_data.get("explanation", "")
        missing_keywords = ats_data.get("missing_keywords", [])
        if explanation:
            st.markdown(f"**What held your original score back**\n\n{explanation}")
        if missing_keywords:
            chips = "".join(f'<span class="cl-chip">{html.escape(str(kw))}</span>' for kw in missing_keywords)
            st.markdown("**Missing or under-represented skills**")
            st.markdown(f'<div class="cl-chips">{chips}</div>', unsafe_allow_html=True)
            st.caption("Only add these to your resume if you genuinely have the experience.")
        with st.expander("Raw agent output"):
            st.code(ats_data.get("llm_feedback", ""), language=None)

    with tab_review:
        if not suggestions:
            st.success("No issues found. Your resume reads cleanly.")
        else:
            st.caption("Click Apply to update your tailored resume with a fix.")
            for i, sug in enumerate(suggestions):
                issue = sug.get("issue", "Suggestion")
                current_text = sug.get("current_text", "")
                suggested_fix = sug.get("suggested_fix", "")
                resume_now = st.session_state.docs["resume"]

                with st.container(border=True):
                    st.markdown(f"**{issue}**")
                    col_a, col_b, col_c = st.columns([2, 2, 1])
                    with col_a:
                        st.caption("Current")
                        st.code(current_text, language=None, wrap_lines=True)
                    with col_b:
                        st.caption("Suggested")
                        st.code(suggested_fix, language=None, wrap_lines=True)
                    with col_c:
                        st.write("")
                        if current_text and current_text not in resume_now:
                            st.success("Applied")
                        elif st.button("Apply", key=f"apply_{i}", width="stretch"):
                            if current_text and current_text in resume_now:
                                set_document("resume", resume_now.replace(current_text, suggested_fix, 1))
                                st.rerun()
                            else:
                                st.warning("Couldn't find an exact match to apply automatically. Edit it manually.")

    with tab_draft:
        st.caption("The Resume Writer's first draft, before the Human Optimizer polished it.")
        st.markdown(resume_to_html(workflow["resume_writer"]["generated_resume"], template), unsafe_allow_html=True)

# ------------------------------------------------------------------
# How it works + footer
# ------------------------------------------------------------------
st.write("")
with st.expander(f"How {APP_NAME} works — an {len(PIPELINE_STEPS)}-step AI pipeline"):
    st.markdown("\n".join(
        f"{i}. **{name}** — {description}" for i, (name, description) in enumerate(PIPELINE_STEPS, start=1)
    ))

st.markdown(f"""
<div class="cl-footer">
  <div>&copy; {date.today().year} {APP_NAME}. Built by Madhav G.</div>
  <div>Your data is processed only to generate your results and is never stored.</div>
</div>
""", unsafe_allow_html=True)
