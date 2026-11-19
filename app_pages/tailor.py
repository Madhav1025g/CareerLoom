"""Tailor page: the main CareerLoom workflow (inputs -> 8-step pipeline -> results)."""
import uuid

import altair as alt
import pandas as pd
import streamlit as st

import main
from main import (
    APP_NAME, COVER_LETTER_TONES, PIPELINE_STEPS, LLMBusyError, LLMUnavailableError, ResumeGenerationError,
    add_skill_to_resume, ats_breakdown, cover_letter_agent, evaluate_requirements, interview_prep_agent, log_event,
    orchestrator, requirement_cache_key,
)
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
from document_builder import pdf_page_count
from ui_common import (
    PROGRESS_STAGES, busy_message, chart_palette, chips, extract_text_from_upload, file_stem, increment_counter,
    progress_stage, record_feedback, requirement_checklist, score_band, step_tracker_html, text_quality_issues,
    verdict_card,
)

# ------------------------------------------------------------------
# Header + hero
# ------------------------------------------------------------------
st.markdown(f"""
<div class="cl-hero">
  <div class="cl-eyebrow">AI career document platform &middot; Free, no sign-up</div>
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
    <div class="cl-feature-text">A {len(PIPELINE_STEPS)}-step AI pipeline tailors your resume without dropping experience, plus a half-page recruiter snapshot.</div>
  </div>
  <div class="cl-feature">
    <div class="cl-feature-title">Recruiter-ready exports</div>
    <div class="cl-feature-text">Edit on the page, pick one of {len(TEMPLATES)} professional templates, and download PDF or Word.</div>
  </div>
</div>
""", unsafe_allow_html=True)

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

SAMPLE_JD = """Backend Software Engineer

We are hiring a Backend Software Engineer to build high-traffic REST APIs in Python and FastAPI.
You will design microservices on AWS, including serverless workloads, and own containerization
and CI/CD pipelines for your services. You'll work in an Agile team with product and data partners.

Requirements: 3+ years of backend development, strong Python, experience with AWS, Docker,
CI/CD, and PostgreSQL.
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
                issues = text_quality_issues(resume_text) if resume_text else []
                if resume_text and not issues:
                    st.success(f"Loaded {uploaded_file.name} ({len(resume_text):,} characters)")
                elif resume_text:
                    st.warning(f"We loaded {uploaded_file.name}, but the text may not have come through cleanly:\n\n"
                               + "\n".join(f"- {issue}" for issue in issues)
                               + "\n\nCheck the text below. If it looks scrambled, paste your resume with “Paste text” "
                                 "or upload a DOCX for better results.")
                    with st.expander("Preview the text we extracted"):
                        st.text(resume_text[:3000] + ("\n..." if len(resume_text) > 3000 else ""))
                else:
                    st.error("We couldn't read that file. Try a DOCX or TXT version instead.")
            elif st.session_state.resume_text_area:
                resume_text = st.session_state.resume_text_area
                st.info("Using the example resume. Switch to “Paste text” to view or edit it.")
        else:
            resume_text = st.text_area("Paste your resume", height=240, key="resume_text_area")
        if resume_text:
            st.session_state.current_resume_text = resume_text

with right:
    with st.container(border=True):
        st.markdown('<div class="cl-card-title">Target job <span class="cl-optional">(recommended)</span></div>',
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
        tracker = st.empty()
        stage = {"index": 0}

        def show_progress(message: str, done: bool = False):
            stage["index"] = progress_stage(message, stage["index"])
            completed = len(PROGRESS_STAGES) if done else stage["index"]
            with tracker.container(border=True):
                st.markdown('<div class="cl-card-title">Generating your application</div>', unsafe_allow_html=True)
                st.caption("This usually takes 30–60 seconds. Please keep this tab open.")
                st.markdown(step_tracker_html(stage["index"], done=done), unsafe_allow_html=True)
                st.progress(min(1.0, (completed + 0.5) / len(PROGRESS_STAGES)) if not done else 1.0,
                            text=message)

        show_progress("Starting...")
        try:
            result = orchestrator(user_request, request_id, progress_callback=show_progress)
            tracker.empty()
        except LLMBusyError as exc:
            tracker.empty()
            st.warning(busy_message(exc))
        except LLMUnavailableError:
            tracker.empty()
            st.error("Our AI service is temporarily unavailable. Please try again in a minute.")
        except ResumeGenerationError:
            tracker.empty()
            st.error("We couldn't generate a complete resume this time. This occasionally happens with long "
                     "resumes. Please try again; this attempt didn't count toward your limit.")
        except Exception as exc:
            log_event(f"{request_id}: unexpected error ({type(exc).__name__})")
            tracker.empty()
            st.error("Something went wrong while generating your application. Please try again.")

        if result is not None:
            st.toast("Your application is ready.", icon=":material/check_circle:")
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
            st.session_state.last_request = user_request
            match = workflow.get("requirement_match") or {}
            if match.get("requirements"):
                cache = st.session_state.setdefault("req_eval_cache", {})
                cache[requirement_cache_key(resume_text, match["requirements"])] = match["before"]
                # The generated "after" check is capped by the original (see evaluate_requirements); store it under
                # the uncapped key the page looks up, so user re-checks after edits are judged on their own.
                cache[requirement_cache_key(st.session_state.docs["resume"], match["requirements"],
                                            resume_text)] = match["after"]
            st.session_state.letter_tone = "Formal"
            st.session_state.pop("interview_prep", None)

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
        if doc_key != "cover_letter":
            page_length_notice(pdf, noun, template)
        st.divider()
        if text != st.session_state.originals[doc_key]:
            if st.button("Undo all edits", width="stretch", key=f"reset_{doc_key}"):
                set_document(doc_key, st.session_state.originals[doc_key])
                st.rerun()
        if below_downloads:
            below_downloads()


def use_compact_template():
    st.session_state.template = "Compact"


def page_length_notice(pdf: bytes, noun: str, template: str):
    """Recruiters expect one page (two for 10+ years of experience); say so when the PDF runs longer."""
    pages = pdf_page_count(pdf)
    years = int(st.session_state.get("last_request", {}).get("experience_years") or 0)
    limit = 1 if noun == "recruiter snapshot" or years < 10 else 2
    if pages <= limit:
        st.caption(f"PDF length: {pages} page{'s' if pages > 1 else ''}")
        return
    advice = ("The snapshot works best on a single page." if noun == "recruiter snapshot" else
              "Most recruiters expect one page for under 10 years of experience." if limit == 1 else
              "Even with 10+ years of experience, recruiters rarely read past page two.")
    st.warning(f"Your {noun} PDF is {pages} pages. {advice}", icon=":material/description:")
    if template != "Compact":
        st.button("Try the Compact template", on_click=use_compact_template, width="stretch",
                  key=f"compact_{noun}")
    else:
        st.caption("Trim older roles or merge similar bullets with Edit to shorten it.")


# Score changes this small are within the scorer's normal variation — don't present them as a gain or loss.
SCORE_NOISE = 2


def change_label(change: int) -> str:
    return "About the same as original" if abs(change) <= SCORE_NOISE else f"{change:+d} vs. original"


def score_rows(before: dict, after: dict, short: bool = False) -> list[tuple[str, int, int]]:
    """Rows for the before/after charts. `before`/`after` may carry a "requirement_score" too."""
    names = (("Requirements", "ATS", "Keyword", "Semantic") if short
             else ("Requirement match", "ATS match", "Keyword match", "Semantic match"))
    rows = []
    if before.get("requirement_score") is not None and after.get("requirement_score") is not None:
        rows.append((names[0], before["requirement_score"], after["requirement_score"]))
    rows += [(names[1], before["ats_score"], after["ats_score"]),
             (names[2], before["keyword_score"], after["keyword_score"])]
    if before.get("semantic_score") is not None and after.get("semantic_score") is not None:
        rows.append((names[3], before["semantic_score"], after["semantic_score"]))
    return rows


def ats_bar_chart(before: dict, after: dict):
    """Compact grouped bars (original vs. tailored) sized for the narrow download column."""
    rows = score_rows(before, after, short=True)
    long = pd.DataFrame(
        [(m, version, score, f"{a - b:+d}") for m, b, a in rows for version, score in (("Before", b), ("After", a))],
        columns=["Measure", "Version", "Score", "Change"],
    )
    order = [m for m, _, _ in rows]
    c = chart_palette()
    encoding = dict(
        y=alt.Y("Measure:N", sort=order, title=None, scale=alt.Scale(paddingInner=0.3),
                axis=alt.Axis(ticks=False, domain=False, labelColor=c["text"], labelFontSize=12, labelPadding=6)),
        yOffset=alt.YOffset("Version:N", sort=["Before", "After"], scale=alt.Scale(paddingInner=0.12)),
        # Extra room past 100 keeps the value labels at the bar tips inside the chart.
        x=alt.X("Score:Q", title=None, scale=alt.Scale(domain=[0, 118]),
                axis=alt.Axis(values=[0, 50, 100], gridColor=c["grid"], domain=False, ticks=False, labelColor=c["muted"])),
    )
    bars = alt.Chart(long).mark_bar(cornerRadiusEnd=4).encode(
        **encoding,
        color=alt.Color("Version:N", scale=alt.Scale(domain=["Before", "After"], range=[c["before"], c["after"]]),
                        legend=alt.Legend(title=None, orient="top", direction="horizontal", labelFontSize=11,
                                          labelColor=c["text"], symbolType="square", symbolSize=70,
                                          labelLimit=0, columnPadding=8, symbolOffset=0, offset=4)),
        tooltip=[alt.Tooltip("Measure:N"), alt.Tooltip("Version:N", title="Resume"), alt.Tooltip("Score:Q"),
                 alt.Tooltip("Change:N", title="Change after tailoring")],
    )
    labels = alt.Chart(long).mark_text(align="left", dx=4, fontSize=11, color=c["text"]).encode(
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
    c = chart_palette()
    y = alt.Y("Measure:N", sort=order, title=None,
              axis=alt.Axis(labelFontSize=13, labelColor=c["text"], ticks=False, domain=False, labelPadding=12, labelLimit=220))
    x_scale = alt.Scale(domain=[0, 100])
    x_axis = alt.Axis(values=[0, 25, 50, 75, 100], gridColor=c["grid"], domain=False, ticks=False,
                      labelColor=c["muted"], titleColor=c["muted"], titleFontWeight="normal")

    rule = alt.Chart(wide).mark_rule(color=c["rule"], strokeWidth=2).encode(
        y=y, x=alt.X("Original:Q", scale=x_scale, axis=x_axis, title="Score (0–100)"), x2="Tailored:Q",
    )
    points = alt.Chart(long).mark_circle(size=190, opacity=1, stroke=c["point_stroke"], strokeWidth=2).encode(
        y=y,
        x=alt.X("Score:Q", scale=x_scale),
        color=alt.Color("Version:N", scale=alt.Scale(domain=["Original", "Tailored"], range=[c["before"], c["after"]]),
                        legend=alt.Legend(title=None, orient="top", direction="horizontal", labelFontSize=12,
                                          labelColor=c["text"], symbolSize=140, symbolStrokeWidth=0)),
        tooltip=[alt.Tooltip("Measure:N"), alt.Tooltip("Version:N", title="Resume"),
                 alt.Tooltip("Score:Q"), alt.Tooltip("Change:N", title="Change after tailoring")],
    )
    # Selective direct label: only the tailored endpoint, with the change.
    labels = alt.Chart(wide).mark_text(dy=-17, fontSize=12, fontWeight=600, color=c["ink"]).encode(
        y=y, x=alt.X("Tailored:Q", scale=x_scale), text="Label:N",
    )
    chart = (rule + points + labels).properties(height=78 * len(rows) + 40)
    return chart.configure_view(strokeWidth=0), wide[["Measure", "Original", "Tailored", "Change"]]

def live_scores(text: str, request: dict, job_keywords: list[str]) -> dict:
    """Re-score the current resume text (no AI call). Memoized per session, so reruns stay instant."""
    cache = st.session_state.setdefault("score_cache", {})
    key = hash((text, request.get("job_description"), tuple(request.get("skills", [])), tuple(job_keywords)))
    if key not in cache:
        cache[key] = ats_breakdown(text, request.get("job_description"), request.get("skills", []), job_keywords)
    return cache[key]


def run_on_demand(label: str, fn, *args):
    """Run an on-demand AI feature with a spinner and friendly errors. Returns None on failure."""
    with st.spinner(label):
        try:
            return fn(*args)
        except LLMBusyError as exc:
            st.warning(busy_message(exc))
        except LLMUnavailableError:
            st.error("Our AI service is temporarily unavailable. Please try again in a minute.")
        except Exception as exc:
            log_event(f"on-demand feature failed ({type(exc).__name__})")
            st.error("Something went wrong. Please try again.")
    return None


def interview_prep_text(prep: dict, full_name: str) -> str:
    parts = [f"Interview prep for {full_name}"]
    for i, q in enumerate(prep.get("questions", []), start=1):
        answer = q.get("answer") if isinstance(q.get("answer"), dict) else {}
        parts.append(
            f"{i}. [{q.get('category', 'Question')}] {q.get('question', '')}\n"
            f"Why they ask: {q.get('why_they_ask', '')}\n"
            + "\n".join(f"{k.title()}: {answer.get(k, '')}" for k in ("situation", "task", "action", "result"))
        )
    return "\n\n".join(parts)

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
    request = st.session_state.get("last_request", {})
    job_keywords = ats_data.get("job_keywords", [])
    edited = st.session_state.docs["resume"] != st.session_state.originals["resume"]
    if request:
        # Scores follow the resume as it is now — including edits, applied fixes, and added skills.
        live = live_scores(st.session_state.docs["resume"], request, job_keywords)
        after = {"ats_score": live["overall"], "keyword_score": live["keyword"], "semantic_score": live["semantic"]}
    else:
        live = {"covered": [], "missing": ats_data.get("still_missing", [])}
        after = ats_data.get("after", before)
    # Requirement match: judged by AI, so it only updates on generation or when the user re-checks after edits.
    req_data = workflow.get("requirement_match") or {}
    requirements = req_data.get("requirements", [])
    req_before = req_data.get("before") or {}
    req_cache = st.session_state.setdefault("req_eval_cache", {})
    # Years of experience always come from the resume the user supplied, never from AI-written text.
    years_source_text = request.get("resume_text") or ""
    req_current = (req_cache.get(requirement_cache_key(st.session_state.docs["resume"], requirements, years_source_text))
                   if requirements else None)
    req_stale = bool(requirements) and req_current is None
    req_after = req_current or req_data.get("after") or {}
    before = {**before, "requirement_score": req_before.get("score")}
    after = {**after, "requirement_score": req_after.get("score")}

    completeness = workflow.get("completeness_check", {})
    suggestions = workflow["reviewer"].get("suggestions", [])
    analyzer = workflow.get("analyzer", {}) if isinstance(workflow.get("analyzer"), dict) else {}

    st.write("")
    head_col, feedback_col = st.columns([3, 1], vertical_alignment="bottom")
    with head_col:
        st.markdown(f'<div class="cl-section-title">Your results</div>'
                    f'<div class="cl-section-sub">Generated in {result["execution_time"]} seconds.</div>',
                    unsafe_allow_html=True)
    with feedback_col:
        st.caption("Were these results helpful?")
        rating = st.feedback("thumbs", key=f"feedback_{result['request_id']}")
        sent_key = f"feedback_sent_{result['request_id']}"
        if rating is not None and not st.session_state.get(sent_key):
            record_feedback(helpful=rating == 1)  # anonymous count only — no content is sent
            st.session_state[sent_key] = True
            st.toast("Thanks for your feedback!")

    verdict_card(after["requirement_score"], req_after.get("items", []), after["ats_score"],
                 has_job=bool(request.get("job_description")), stale=req_stale)

    change = after["ats_score"] - before["ats_score"]
    meaningful = abs(change) > SCORE_NOISE
    m1, m2, m3, m4 = st.columns(4)
    if after["requirement_score"] is not None:
        req_change = after["requirement_score"] - before["requirement_score"]
        req_meaningful = abs(req_change) > SCORE_NOISE and not req_stale
        m1.metric("Requirement match", f"{after['requirement_score']}/100",
                  delta="Re-check after your edits" if req_stale else change_label(req_change),
                  delta_color="normal" if req_meaningful else "off", delta_arrow="auto" if req_meaningful else "off",
                  border=True, help=f"{score_band(after['requirement_score'])[0]}. How a recruiter would judge your "
                                    "resume against each of the job's requirements. 80+ strong, 65–79 good, "
                                    "45–64 fair, under 45 a stretch.")
    else:
        m1.metric("Requirement match", "—", border=True,
                  help="Add a job description to see how you match its requirements.")
    m2.metric("ATS match", f"{after['ats_score']}/100", delta=change_label(change),
              delta_color="normal" if meaningful else "off", delta_arrow="auto" if meaningful else "off", border=True,
              help=f"{score_band(after['ats_score'])[0]}. Job keywords + semantic similarity, the way ATS software "
                   "searches. Updates live as you edit. 80+ strong, 65–79 good, 45–64 fair, under 45 a stretch.")
    m3.metric("Experience preserved", f"{completeness.get('completeness_pct', 100)}%", border=True)
    m4.metric("Candidate level", analyzer.get("candidate_level") or "—", border=True)

    style_col, style_note_col = st.columns([2, 3], vertical_alignment="center")
    with style_col:
        template = st.segmented_control(
            "Document style", list(TEMPLATES), default=DEFAULT_TEMPLATE, key="template",
        ) or DEFAULT_TEMPLATE
    with style_note_col:
        st.caption(TEMPLATES[template]["description"] + " Applies to the preview and every download.")

    tab_resume, tab_snapshot, tab_letter, tab_prep, tab_ats, tab_review, tab_draft = st.tabs(
        ["Tailored resume", "Recruiter snapshot", "Cover letter", "Interview prep", "Job match",
         "Review suggestions", "First draft"],
        key="result_tab", on_change="rerun",  # stateful: buttons inside a tab don't jump back to the first tab
    )

    with tab_resume:
        guard = workflow.get("claims_guard") or {}
        if guard.get("removed"):
            st.info("We removed claims about " + ", ".join(guard["removed"]) + " that your original resume didn't "
                    "support. If you genuinely have that experience, add it with Edit or \"I have this\" in Job match.")
        if guard.get("removed_numbers"):
            st.info("We removed figures (" + ", ".join(guard["removed_numbers"]) + ") the AI added that aren't in "
                    "your original resume. Only include numbers you can back up in an interview.")
        if guard.get("unresolved"):
            st.warning("This version still mentions " + ", ".join(guard["unresolved"]) + ", which your original "
                       "resume doesn't show. Remove it with Edit unless it's genuinely true.")
        if completeness.get("possibly_missing"):
            st.warning(
                f"Content check: {completeness['completeness_pct']}% of the entries we detected in your original "
                "resume appear in this version. Please double-check these lines weren't dropped:"
            )
            for line in completeness["possibly_missing"]:
                st.caption(f"• {line}")
        def resume_score_chart():
            st.markdown('<div class="cl-card-title">Match scores</div>', unsafe_allow_html=True)
            st.caption(f"Before vs. after tailoring{' (with your edits)' if edited else ''}. "
                       "Details in the Job match tab.")
            st.altair_chart(ats_bar_chart(before, after), width="stretch")
            if workflow["human_optimizer"].get("fallback_reason") == "lower ATS score":
                st.caption("We kept the first draft because it scored higher than the polished version.")

        document_panel("resume", "resume", "Resume", template, stem, full_name, below_downloads=resume_score_chart)

    with tab_snapshot:
        st.caption("A half-page version a recruiter can scan in 10–15 seconds. Send it alongside your full "
                   "resume, or paste it into a message to a recruiter.")
        document_panel("snapshot", "recruiter snapshot", "Recruiter_Snapshot", template, stem, full_name)

    with tab_letter:
        tone_col, rewrite_col = st.columns([3, 1], vertical_alignment="bottom")
        with tone_col:
            current_tone = st.session_state.get("letter_tone", "Formal")
            tone = st.segmented_control("Tone", list(COVER_LETTER_TONES), default=current_tone, key="tone_choice") or current_tone
        with rewrite_col:
            if st.button(f"Rewrite as {tone.lower()}", width="stretch", disabled=tone == current_tone or not request):
                letter = run_on_demand(f"Rewriting your cover letter ({tone.lower()})...",
                                       cover_letter_agent, request, None, tone)
                if letter:
                    st.session_state.originals["cover_letter"] = letter["cover_letter"]
                    set_document("cover_letter", letter["cover_letter"])
                    st.session_state.letter_tone = tone
                    st.rerun()
        document_panel("cover_letter", "cover letter", "Cover_Letter", template, stem, full_name)

    with tab_prep:
        prep = st.session_state.get("interview_prep")
        if not prep:
            st.markdown("Get **8 likely interview questions for this job**, each with a suggested answer in the "
                        "STAR format (Situation, Task, Action, Result) built from your own resume.")
            if st.button("Generate interview prep", type="primary", disabled=not request):
                prep = run_on_demand("Preparing your interview questions...",
                                     interview_prep_agent, request, st.session_state.docs["resume"])
                if prep:
                    st.session_state.interview_prep = prep
                    st.rerun()
        else:
            questions = prep.get("questions", [])
            if not questions:
                st.markdown(prep.get("raw", ""))
            for i, q in enumerate(questions, start=1):
                answer = q.get("answer") if isinstance(q.get("answer"), dict) else {}
                with st.expander(f"**{i}. {q.get('question', '')}**  ·  {q.get('category', '')}", expanded=i == 1):
                    if q.get("why_they_ask"):
                        st.caption(f"Why they ask: {q['why_they_ask']}")
                    for part in ("situation", "task", "action", "result"):
                        if answer.get(part):
                            st.markdown(f"**{part.title()}:** {answer[part]}")
            text = interview_prep_text(prep, full_name)
            word_col, txt_col, again_col = st.columns(3)
            word_col.download_button("Download (Word)", data=build_letter_docx(text, "", template),
                                   file_name=f"{stem}_Interview_Prep.docx", width="stretch",
                                   mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document")
            txt_col.download_button("Download (text)", data=text, file_name=f"{stem}_Interview_Prep.txt",
                                     mime="text/plain", width="stretch")
            if again_col.button("Generate new questions", width="stretch"):
                st.session_state.pop("interview_prep")
                st.rerun()

    with tab_ats:
        # ---- Requirement match: the recruiter's scorecard
        st.markdown('<div class="cl-card-title">Requirement match</div>', unsafe_allow_html=True)
        if not requirements:
            st.info("Add a job description to see how your resume matches each of the job's requirements."
                    if not request.get("job_description") else
                    "We couldn't read this job's requirements this time. Try generating again.")
        else:
            if req_stale:
                note_col, button_col = st.columns([3, 1], vertical_alignment="center")
                note_col.info("You've edited your resume since the requirements were last checked.")
                if button_col.button("Re-check requirements", type="primary", width="stretch"):
                    if run_on_demand("Re-checking each requirement...", evaluate_requirements,
                                     st.session_state.docs["resume"], requirements, req_cache, years_source_text):
                        st.rerun()
            items = req_after.get("items", [])
            met = sum(i["status"] == "met" for i in items)
            partial = sum(i["status"] == "partial" for i in items)
            st.markdown(f"**{req_after.get('score')}/100** &nbsp;·&nbsp; {met} met, {partial} partial, "
                        f"{len(items) - met - partial} missing of {len(items)} requirements")
            for item in items:
                if item["category"] in ("experience_years", "education") and item["status"] != "met" \
                        and item["importance"] == "required":
                    st.warning(item["reason"])
            requirement_checklist(items, req_before.get("items"))
            st.caption("Required items count 3×, preferred 1×, soft skills 0.5×. Met earns full credit, partial half; "
                       "years of experience earn credit in proportion to the gap. Evidence is quoted from your resume "
                       "and checked to make sure it's really there.")

        # ---- ATS match: how software searches
        st.divider()
        chart, table = ats_dumbbell_chart(before, after)
        overall_note = "about the same overall" if not meaningful else f"{change:+d} points overall"
        st.markdown(f"**All scores: original vs. tailored resume** &nbsp;·&nbsp; ATS match {overall_note}")
        st.altair_chart(chart, width="stretch")
        if ats_data.get("job_keywords"):
            st.caption("Both versions are scored against the same list of the job's key terms. Keyword match is the "
                       "share of those terms found in your resume (60% of the score); semantic match measures how "
                       "closely your wording matches the job description (40%).")
        else:
            st.caption("Both versions are scored the same way. Without a job description, keyword match uses the "
                       "skills you entered.")
        with st.expander("View as table"):
            st.dataframe(table, hide_index=True, width="stretch")

        st.write("")
        covered_before = ats_data.get("covered_keywords", [])
        still_missing = live["missing"] if request else ats_data.get("still_missing", ats_data.get("missing_keywords", []))
        if job_keywords:
            st.markdown(f"**Job keyword coverage:** {len(job_keywords) - len(still_missing)} of {len(job_keywords)} "
                        f"key terms (original resume: {len(covered_before)})")
        lost = [k for k in covered_before if k in still_missing]
        if lost:
            st.warning("These job keywords were in your original resume but not in the tailored version. "
                       "Add them back using Edit on the Tailored resume tab: " + ", ".join(lost))
        added = [k for k in job_keywords if k not in covered_before and k not in still_missing]
        if added:
            st.markdown("**Now included after tailoring**")
            chips(added, "cl-chip-good")
        explanation = ats_data.get("explanation", "")
        if ats_data.get("keyword_source") == "skills" and request.get("job_description"):
            st.info(explanation)
        elif explanation:
            st.markdown(f"**Your original resume vs. this job**\n\n{explanation}")
        if still_missing:
            picked = st.pills(
                "**Still missing** — click any skill you genuinely have to add it to your resume",
                still_missing, selection_mode="single", key=f"have_skill_{st.session_state.doc_versions['resume']}",
            )
            if picked:
                set_document("resume", add_skill_to_resume(st.session_state.docs["resume"], picked))
                st.toast(f"Added {picked} to your skills section. Your score has been updated.")
                st.rerun()
            st.caption("CareerLoom never adds skills on its own. Only add a skill here if you genuinely have it — "
                       "recruiters may ask about it in an interview.")
        if job_keywords:
            with st.expander(f"The {len(job_keywords)} key terms used for scoring"):
                st.caption("Extracted once from the job description, so this job is scored against the same list "
                           "everywhere in CareerLoom, including Compare jobs.")
                chips(job_keywords)

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
# Landing content: shown until the first results exist (results then take this space)
# ------------------------------------------------------------------
if "last_result" not in st.session_state:
    st.write("")
    st.markdown('<div class="cl-section-title">See the difference</div>'
                '<div class="cl-section-sub">An example from the sample resume above (a fictional candidate). Same '
                'facts and the same numbers, rewritten in the language of the job.</div>', unsafe_allow_html=True)
    st.markdown('''
<div class="cl-compare">
  <div class="cl-sample">
    <div class="cl-sample-label">Original resume</div>
    <ul>
      <li>Built and maintained REST APIs serving 1M+ daily requests using Python and FastAPI</li>
      <li>Deployed microservices on AWS Lambda and ECS, reducing infra costs by 20%</li>
      <li>Automated CI/CD pipelines using GitHub Actions and Docker</li>
    </ul>
    <div class="cl-sample-foot">Job asks for: high-traffic APIs, serverless workloads on AWS, containerization, CI/CD.</div>
  </div>
  <div class="cl-sample">
    <div class="cl-sample-label">Tailored for the job</div>
    <ul>
      <li>Built and maintained <mark>high-traffic</mark> REST APIs serving 1M+ daily requests using Python and FastAPI</li>
      <li>Deployed microservices on AWS, including <mark>serverless workloads</mark> on Lambda and ECS, reducing infrastructure costs by 20%</li>
      <li>Automated CI/CD pipelines and <mark>containerization</mark> using GitHub Actions and Docker</li>
    </ul>
    <div class="cl-sample-foot">Highlighted: the job's own terms, matched to experience the candidate already had.
    Nothing new was claimed.</div>
  </div>
</div>''', unsafe_allow_html=True)

    st.write("")
    st.markdown('<div class="cl-section-title">Frequently asked questions</div>', unsafe_allow_html=True)
    faq = [
        ("Is my resume stored anywhere?",
         f"No. {APP_NAME} has no accounts and no resume database. Your resume is sent to our AI provider only to "
         "generate your results, and everything is discarded when you close the tab. See the Privacy page for details."),
        ("Will it invent experience, skills, or numbers?",
         "No. Every result passes a claims check: skills, years of experience, and figures that aren't in your "
         "original resume are removed, and we tell you what was removed. Missing skills are listed for you to add "
         "yourself, only if you genuinely have them."),
        ("Why is my score lower than on other sites?",
         "We score like a recruiter: each job requirement is checked against evidence quoted from your resume, and "
         "years of experience are calculated from your dates, not guessed. Scores of 65+ are already a good match. "
         "The How we score page explains every number."),
        ("Is it free?",
         f"Yes, with no sign-up. To keep it free for everyone, each session can generate {MAX_GENERATIONS_PER_SESSION} "
         "applications. Edits, template changes, downloads, and re-scoring don't count."),
        ("Which files can I upload?",
         "PDF, Word (DOCX), or plain text. Scanned or image-only PDFs have no readable text, and two-column layouts "
         "sometimes come out scrambled. We'll warn you if that happens, and you can paste your resume instead."),
        ("Does a high score guarantee an interview?",
         "No tool can promise that. A high score means your resume clearly shows what the job asks for, which helps "
         "you get past ATS filters and a recruiter's first scan."),
    ]
    for question, answer in faq:
        with st.expander(question):
            st.markdown(answer)
