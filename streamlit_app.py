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

from main import APP_NAME, PIPELINE_STEPS, LLMUnavailableError, log_event, orchestrator
from document_builder import (
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

.cf-nav { display: flex; align-items: center; justify-content: space-between; margin-bottom: 2.4rem; }
.cf-brand { display: flex; align-items: center; gap: 0.6rem; font-weight: 700; font-size: 1.25rem; color: #0F172A; letter-spacing: -0.01em; }
.cf-mark { display: inline-flex; align-items: center; justify-content: center; width: 34px; height: 34px;
           border-radius: 8px; background: #1E3A8A; color: #fff; font-size: 0.85rem; font-weight: 700; }
.cf-mark span { color: #F59E0B; }
.cf-pill { font-size: 0.78rem; font-weight: 600; color: #1E3A8A; background: #EEF2FF; border: 1px solid #DCE3F9;
           padding: 0.3rem 0.75rem; border-radius: 999px; }

.cf-hero { padding: 0.5rem 0 1.8rem 0; max-width: 780px; }
.cf-eyebrow { text-transform: uppercase; letter-spacing: 0.12em; font-size: 0.75rem; font-weight: 700; color: #B45309; margin-bottom: 0.7rem; }
.cf-h1 { font-size: 2.6rem; line-height: 1.12; font-weight: 700; color: #0F172A; letter-spacing: -0.025em; margin-bottom: 0.9rem; }
.cf-lead { font-size: 1.08rem; line-height: 1.6; color: #475569; }

.cf-features { display: grid; grid-template-columns: repeat(auto-fit, minmax(230px, 1fr)); gap: 1rem; margin-bottom: 2.6rem; }
.cf-feature { border: 1px solid #E3E7EF; border-radius: 12px; padding: 1.1rem 1.2rem; background: #FAFBFD; }
.cf-feature-title { font-weight: 600; color: #0F172A; margin-bottom: 0.3rem; }
.cf-feature-text { font-size: 0.9rem; color: #64748B; line-height: 1.5; }

.cf-section-title { font-size: 1.45rem; font-weight: 700; color: #0F172A; letter-spacing: -0.015em; margin: 0.4rem 0 0.2rem 0; }
.cf-section-sub { color: #64748B; font-size: 0.95rem; margin-bottom: 1rem; }
.cf-card-title { font-weight: 600; font-size: 1rem; color: #0F172A; margin-bottom: 0.2rem; }
.cf-privacy { font-size: 0.82rem; color: #64748B; text-align: center; margin-top: 0.6rem; }

.cf-doc { background: #fff; border: 1px solid #E3E7EF; border-radius: 10px; padding: 2.2rem 2.5rem;
          box-shadow: 0 1px 3px rgba(15,23,42,.05), 0 10px 30px rgba(15,23,42,.06);
          color: #111827; font-size: 0.9rem; line-height: 1.5; max-height: 1000px; overflow-y: auto; }
.cf-doc p { margin: 0.12rem 0 !important; font-size: 0.9rem !important; }
.cf-doc ul { margin: 0.15rem 0 0.35rem 1.1rem !important; padding: 0 !important; }
.cf-doc li { margin: 0.08rem 0 !important; font-size: 0.9rem !important; }
.cf-name { text-align: center; font-size: 1.6rem; font-weight: 700; color: #1E3A8A; letter-spacing: -0.01em; }
.cf-contact { text-align: center; color: #64748B; font-size: 0.8rem; margin-top: 0.15rem; }
.cf-heading { margin: 1.1rem 0 0.45rem 0; padding-bottom: 0.2rem; border-bottom: 1.5px solid #1E3A8A;
              color: #1E3A8A; font-weight: 700; font-size: 0.8rem; letter-spacing: 0.08em; }
.cf-entry { font-weight: 600; margin-top: 0.55rem; }
.cf-letter { padding: 2.6rem 3rem; }
.cf-letter p { margin: 0 0 0.9rem 0 !important; }

.cf-chips { display: flex; flex-wrap: wrap; gap: 0.4rem; margin: 0.4rem 0 1rem 0; }
.cf-chip { font-size: 0.8rem; font-weight: 500; color: #9A3412; background: #FFF7ED; border: 1px solid #FED7AA;
           border-radius: 999px; padding: 0.2rem 0.65rem; }

.cf-footer { border-top: 1px solid #E3E7EF; margin-top: 3rem; padding-top: 1.2rem; color: #94A3B8; font-size: 0.82rem;
             display: flex; justify-content: space-between; flex-wrap: wrap; gap: 0.5rem; }
</style>
""", unsafe_allow_html=True)

# ------------------------------------------------------------------
# Header + hero
# ------------------------------------------------------------------
st.markdown(f"""
<div class="cf-nav">
  <div class="cf-brand"><span class="cf-mark">C<span>F</span></span>{APP_NAME}</div>
  <div class="cf-pill">Free &middot; No sign-up required</div>
</div>
<div class="cf-hero">
  <div class="cf-eyebrow">AI career document platform</div>
  <div class="cf-h1">Tailor your resume to every job you apply for.</div>
  <div class="cf-lead">{APP_NAME} reads your resume and the job description, scores your ATS match,
  rewrites your resume for the role, and drafts a matching cover letter &mdash; in about 30 seconds.</div>
</div>
<div class="cf-features">
  <div class="cf-feature">
    <div class="cf-feature-title">ATS match scoring</div>
    <div class="cf-feature-text">Semantic and keyword matching show how well you fit the role and exactly what's missing.</div>
  </div>
  <div class="cf-feature">
    <div class="cf-feature-title">Tailored resume &amp; cover letter</div>
    <div class="cf-feature-text">A seven-step AI pipeline rewrites your resume for the role without dropping your experience.</div>
  </div>
  <div class="cf-feature">
    <div class="cf-feature-title">Recruiter-ready exports</div>
    <div class="cf-feature-text">Download cleanly formatted PDF and Word documents, ready to submit.</div>
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
    st.markdown('<div class="cf-section-title">Build your application</div>'
                '<div class="cf-section-sub">Add your details and resume. A job description unlocks ATS matching and a tailored cover letter.</div>',
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
        st.markdown('<div class="cf-card-title">Your profile</div>', unsafe_allow_html=True)
        col1, col2 = st.columns(2)
        with col1:
            full_name = st.text_input("Full name", key="full_name")
            experience_years = st.number_input("Years of experience", min_value=0, max_value=50, step=1, key="experience_years")
        with col2:
            current_role = st.text_input("Current role", placeholder="e.g. Software Engineer", key="current_role")
            skills_input = st.text_input("Key skills (comma-separated)", placeholder="Python, FastAPI, AWS", key="skills_input")

    with st.container(border=True):
        st.markdown('<div class="cf-card-title">Your resume</div>', unsafe_allow_html=True)
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
        st.markdown('<div class="cf-card-title">Target job <span style="font-weight:400;color:#94A3B8">(recommended)</span></div>',
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
    f'<div class="cf-privacy">Your resume is sent to our AI provider only to generate your results. '
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
            except Exception as exc:
                log_event(f"{request_id}: unexpected error ({type(exc).__name__})")
                status.update(label="Generation failed", state="error")
                st.error("Something went wrong while generating your application. Please try again.")

        if result is not None:
            increment_counter()
            st.session_state.generation_count += 1

            # Store the final resume in session state so Apply-fix buttons can edit it
            # and have the edits persist across reruns.
            st.session_state.editable_resume = result["workflow"]["human_optimizer"]["human_friendly_resume"]
            st.session_state.cover_letter = result["workflow"]["cover_letter"]["cover_letter"]
            st.session_state.last_result = result
            st.session_state.last_full_name = full_name

# ------------------------------------------------------------------
# Results (persist across reruns via session_state, so Apply buttons work)
# ------------------------------------------------------------------
if "last_result" in st.session_state:
    result = st.session_state.last_result
    workflow = result["workflow"]
    full_name = st.session_state.last_full_name
    cover_letter = st.session_state.cover_letter
    stem = file_stem(full_name)

    ats_data = workflow["ats_optimization"]
    completeness = workflow.get("completeness_check", {})
    suggestions = workflow["reviewer"].get("suggestions", [])
    analyzer = workflow.get("analyzer", {}) if isinstance(workflow.get("analyzer"), dict) else {}

    st.write("")
    st.markdown(f'<div class="cf-section-title">Your results</div>'
                f'<div class="cf-section-sub">Generated in {result["execution_time"]} seconds.</div>',
                unsafe_allow_html=True)

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("ATS match", f"{ats_data.get('ats_score', 0)}/100", border=True)
    m2.metric("Experience preserved", f"{completeness.get('completeness_pct', 100)}%", border=True)
    m3.metric("Review suggestions", len(suggestions), border=True)
    m4.metric("Candidate level", analyzer.get("candidate_level") or "—", border=True)

    tab_resume, tab_letter, tab_ats, tab_review, tab_draft = st.tabs(
        ["Tailored resume", "Cover letter", "ATS analysis", "Review suggestions", "First draft"]
    )

    with tab_resume:
        if completeness.get("possibly_missing"):
            st.warning(
                f"Content check: {completeness['completeness_pct']}% of the entries we detected in your original "
                "resume appear in this version. Please double-check these lines weren't dropped:"
            )
            for line in completeness["possibly_missing"]:
                st.caption(f"• {line}")

        doc_col, action_col = st.columns([3, 1], gap="large")
        with doc_col:
            st.markdown(resume_to_html(st.session_state.editable_resume), unsafe_allow_html=True)
        with action_col:
            st.markdown('<div class="cf-card-title">Download</div>', unsafe_allow_html=True)
            st.download_button(
                "PDF", data=build_resume_pdf(st.session_state.editable_resume),
                file_name=f"{stem}_Resume.pdf", mime="application/pdf", type="primary", width="stretch",
            )
            st.download_button(
                "Word (DOCX)", data=build_resume_docx(st.session_state.editable_resume),
                file_name=f"{stem}_Resume.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document", width="stretch",
            )
            st.download_button(
                "Plain text", data=st.session_state.editable_resume,
                file_name=f"{stem}_Resume.txt", mime="text/plain", width="stretch",
            )
            st.divider()
            st.caption("Apply fixes from the Review suggestions tab to update this resume.")
            if st.button("Reset edits", width="stretch"):
                st.session_state.editable_resume = workflow["human_optimizer"]["human_friendly_resume"]
                st.rerun()

    with tab_letter:
        doc_col, action_col = st.columns([3, 1], gap="large")
        with doc_col:
            st.markdown(letter_to_html(cover_letter), unsafe_allow_html=True)
        with action_col:
            st.markdown('<div class="cf-card-title">Download</div>', unsafe_allow_html=True)
            st.download_button(
                "PDF", data=build_letter_pdf(cover_letter, full_name),
                file_name=f"{stem}_Cover_Letter.pdf", mime="application/pdf", type="primary", width="stretch",
            )
            st.download_button(
                "Word (DOCX)", data=build_letter_docx(cover_letter, full_name),
                file_name=f"{stem}_Cover_Letter.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document", width="stretch",
            )
            st.download_button(
                "Plain text", data=cover_letter,
                file_name=f"{stem}_Cover_Letter.txt", mime="text/plain", width="stretch",
            )

    with tab_ats:
        score = ats_data.get("ats_score", 0)
        score_col, detail_col = st.columns([1, 2], gap="large")
        with score_col:
            with st.container(border=True):
                st.metric("ATS match score", f"{score}/100")
                st.progress(score / 100)
                if ats_data.get("semantic_score") is not None:
                    st.caption(f"Keyword match {ats_data.get('keyword_score')} · Semantic match {ats_data['semantic_score']}")
                else:
                    st.caption("Keyword match only. Add a job description for semantic matching.")
        with detail_col:
            explanation = ats_data.get("explanation", "")
            missing_keywords = ats_data.get("missing_keywords", [])
            if explanation:
                st.markdown(f"**Why this score**\n\n{explanation}")
            if missing_keywords:
                chips = "".join(f'<span class="cf-chip">{html.escape(str(kw))}</span>' for kw in missing_keywords)
                st.markdown("**Missing or under-represented skills**")
                st.markdown(f'<div class="cf-chips">{chips}</div>', unsafe_allow_html=True)
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
                        already_applied = current_text and current_text not in st.session_state.editable_resume
                        if already_applied:
                            st.success("Applied")
                        elif st.button("Apply", key=f"apply_{i}", width="stretch"):
                            if current_text and current_text in st.session_state.editable_resume:
                                st.session_state.editable_resume = st.session_state.editable_resume.replace(
                                    current_text, suggested_fix, 1
                                )
                                st.rerun()
                            else:
                                st.warning("Couldn't find an exact match to apply automatically. Edit it manually.")

    with tab_draft:
        st.caption("The Resume Writer's first draft, before the Human Optimizer polished it.")
        st.markdown(resume_to_html(workflow["resume_writer"]["generated_resume"]), unsafe_allow_html=True)

# ------------------------------------------------------------------
# How it works + footer
# ------------------------------------------------------------------
st.write("")
with st.expander(f"How {APP_NAME} works — a {len(PIPELINE_STEPS)}-step AI pipeline"):
    st.markdown("\n".join(
        f"{i}. **{name}** — {description}" for i, (name, description) in enumerate(PIPELINE_STEPS, start=1)
    ))

st.markdown(f"""
<div class="cf-footer">
  <div>&copy; {date.today().year} {APP_NAME}. Built by Madhav G.</div>
  <div>Your data is processed only to generate your results and is never stored.</div>
</div>
""", unsafe_allow_html=True)
