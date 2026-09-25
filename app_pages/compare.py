"""Compare jobs page: score one resume against up to three job descriptions to see where to apply first."""
import altair as alt
import pandas as pd
import streamlit as st

from main import LLMBusyError, LLMUnavailableError, compare_jobs, log_event
from ui_common import busy_message, chips, extract_text_from_upload, page_intro

MAX_JOBS = 3
MAX_COMPARISONS_PER_SESSION = 3

page_intro(
    "Compare jobs",
    "Which job fits you best?",
    "Paste up to three job descriptions. CareerLoom scores your resume against each one — the same way it scores "
    "tailoring — so you can see where you're the strongest match and what each role is missing.",
)

if "comparison_count" not in st.session_state:
    st.session_state.comparison_count = 0

# ------------------------------------------------------------------
# Inputs
# ------------------------------------------------------------------
with st.container(border=True):
    st.markdown('<div class="cl-card-title">Your resume</div>', unsafe_allow_html=True)
    saved = st.session_state.get("current_resume_text")
    options = (["Use my resume from Tailor resume"] if saved else []) + ["Upload a file", "Paste text"]
    source = st.segmented_control("Resume source", options, default=options[0], key="compare_source",
                                  label_visibility="collapsed") or options[0]
    resume_text = None
    if source == "Use my resume from Tailor resume":
        resume_text = saved
        st.caption(f"Using the resume you added on the Tailor resume page ({len(saved):,} characters).")
    elif source == "Upload a file":
        uploaded = st.file_uploader("Upload your resume (PDF, DOCX, or TXT)", type=["pdf", "docx", "txt"], key="compare_upload")
        resume_text = extract_text_from_upload(uploaded) if uploaded else None
    else:
        resume_text = st.text_area("Paste your resume", height=200, key="compare_resume_text")
    skills_input = st.text_input("Key skills (comma-separated, optional)", key="compare_skills",
                                 value=st.session_state.get("skills_input", ""))

job_cols = st.columns(MAX_JOBS, gap="medium")
job_descriptions = []
for i, col in enumerate(job_cols):
    with col, st.container(border=True):
        st.markdown(f'<div class="cl-card-title">Job {i + 1}{" (optional)" if i == 2 else ""}</div>', unsafe_allow_html=True)
        job_descriptions.append(st.text_area(f"Job description {i + 1}", height=260, key=f"compare_jd_{i}",
                                             placeholder="Paste the job description here...", label_visibility="collapsed"))

filled = [jd for jd in job_descriptions if jd.strip()]
remaining = MAX_COMPARISONS_PER_SESSION - st.session_state.comparison_count
if remaining <= 0:
    st.warning(f"You've reached the limit of {MAX_COMPARISONS_PER_SESSION} comparisons for this session. "
               "This keeps the service free for everyone — please come back later.")
    compare_clicked = False
else:
    compare_clicked = st.button("Compare jobs", type="primary", width="stretch")

if compare_clicked:
    if not resume_text:
        st.error("Please add your resume.")
    elif len(filled) < 2:
        st.error("Please paste at least two job descriptions to compare.")
    else:
        skills = [s.strip() for s in skills_input.split(",") if s.strip()]
        with st.spinner(f"Scoring your resume against {len(filled)} jobs..."):
            try:
                st.session_state.comparison = compare_jobs(resume_text, skills, job_descriptions,
                                                           st.session_state.get("current_role", ""))
                st.session_state.comparison_count += 1
            except LLMBusyError as exc:
                st.warning(busy_message(exc))
            except LLMUnavailableError:
                st.error("Our AI service is temporarily unavailable. Please try again in a minute.")
            except Exception as exc:
                log_event(f"compare jobs failed ({type(exc).__name__})")
                st.error("Something went wrong while comparing jobs. Please try again.")

# ------------------------------------------------------------------
# Results
# ------------------------------------------------------------------
results = st.session_state.get("comparison")
if results:
    st.write("")
    st.markdown('<div class="cl-section-title">Your best matches</div>'
                '<div class="cl-section-sub">Ranked by ATS match. Tailoring can raise each score — use the button to '
                'tailor your resume for a job.</div>', unsafe_allow_html=True)

    def job_label(r):
        first_line = next((line.strip() for line in r["job_description"].splitlines() if line.strip()), "")
        title = first_line[:48] + ("…" if len(first_line) > 48 else "")
        return f"Job {r['index'] + 1}: {title}"

    # Grouped bars, one group per job: overall / keyword / semantic
    rows = []
    for r in results:
        for measure, value in (("Overall", r["ats_score"]), ("Keyword", r["keyword_score"]), ("Semantic", r["semantic_score"])):
            if value is not None:
                rows.append((f"Job {r['index'] + 1}", measure, value))
    data = pd.DataFrame(rows, columns=["Job", "Measure", "Score"])
    order = [f"Job {r['index'] + 1}" for r in results]
    encoding = dict(
        y=alt.Y("Job:N", sort=order, title=None, axis=alt.Axis(ticks=False, domain=False, labelColor="#334155",
                                                               labelFontSize=13, labelPadding=8)),
        yOffset=alt.YOffset("Measure:N", sort=["Overall", "Keyword", "Semantic"], scale=alt.Scale(paddingInner=0.12)),
        x=alt.X("Score:Q", title="Score (0–100)", scale=alt.Scale(domain=[0, 108]),
                axis=alt.Axis(values=[0, 25, 50, 75, 100], gridColor="#EEF1F5", domain=False, ticks=False,
                              labelColor="#64748B", titleColor="#64748B", titleFontWeight="normal")),
    )
    bars = alt.Chart(data).mark_bar(cornerRadiusEnd=4).encode(
        **encoding,
        color=alt.Color("Measure:N", sort=["Overall", "Keyword", "Semantic"],
                        scale=alt.Scale(domain=["Overall", "Keyword", "Semantic"], range=["#1E3A8A", "#5B7BC8", "#A9BCE6"]),
                        legend=alt.Legend(title=None, orient="top", direction="horizontal", labelColor="#334155",
                                          symbolType="square")),
        tooltip=["Job:N", "Measure:N", "Score:Q"],
    )
    labels = alt.Chart(data).mark_text(align="left", dx=4, fontSize=11, color="#334155").encode(**encoding, text="Score:Q")
    st.altair_chart((bars + labels).properties(height=alt.Step(16)).configure_view(strokeWidth=0), width="stretch")
    with st.expander("View as table"):
        st.dataframe(data.pivot(index="Job", columns="Measure", values="Score").reindex(order).reset_index(),
                     hide_index=True, width="stretch")

    for rank, r in enumerate(results, start=1):
        with st.container(border=True):
            head, score, action = st.columns([4, 1, 1.4], vertical_alignment="center")
            head.markdown(f'<span class="cl-rank">{rank}</span>**{job_label(r)}**', unsafe_allow_html=True)
            score.metric("ATS match", f"{r['ats_score']}/100", label_visibility="collapsed")
            if action.button("Tailor for this job", key=f"tailor_job_{r['index']}", width="stretch"):
                st.session_state.job_description_area = r["job_description"]
                st.switch_page(st.session_state.pages["tailor"])
            if r.get("keyword_source") == "skills":
                st.info(r["explanation"])
            elif r.get("explanation"):
                st.markdown(r["explanation"])
            if r.get("covered_keywords"):
                st.markdown("**You have**")
                chips(r["covered_keywords"], "cl-chip-good")
            if r.get("missing_keywords"):
                st.markdown("**Missing**")
                chips(r["missing_keywords"])
