"""How we score: a plain-English explanation of the ATS score and the AI pipeline."""
import streamlit as st

from main import APP_NAME, KEYWORD_WEIGHT, PIPELINE_STEPS
from ui_common import page_intro

keyword_pct = round(KEYWORD_WEIGHT * 100)
semantic_pct = 100 - keyword_pct

page_intro(
    "How we score",
    "Two transparent scores",
    f"{APP_NAME} scores your resume the two ways it will actually be read: by a recruiter (or AI screener) checking "
    "the job's requirements, and by ATS software searching for keywords.",
)

st.markdown(f"""
<div class="cl-prose">

### 1. Requirement match — how a recruiter reads your resume
The job description is broken into its requirements (usually 8–18) — for example *"2–10 years of industry
software experience"*, *"strong backend fundamentals"*, *"experience with AWS"* — each marked **required** or
**preferred**. Then each one is checked against your resume **by meaning, not exact words**:

- **Years of experience are calculated in code, not guessed.** We use the figure you state (e.g. "6+ years of
  experience") or add up your job dates (overlapping jobs count once; education is skipped).
  - Within **1 year** of what the job asks is a full match: 2–10 asked, 6 on your resume → met.
  - Fewer years earn credit **in proportion**: 6+ asked, 3 on your resume → half credit, and we tell you why.
  - More years only count against you when the job states an upper limit (e.g. "2–4 years"), since it may read as
    overqualified. "5+ years" has no upper limit.
- **Everything else is judged by AI like a fair recruiter would** — related technologies and demonstrated work
  count, so "built and scaled REST APIs" shows backend fundamentals. Each match must **quote the line from your
  resume** that proves it, and we check the quote really exists; unproven matches are downgraded.
- **Scoring:** required items count 3×, preferred 1×, soft skills 0.5× (and only with evidence). Met earns full
  credit, partial earns half.
- The same resume and job get the **same verdicts** on every page during your visit, including Compare jobs. After
  you edit your resume, use **Re-check requirements** to update it.

### 2. ATS match — how software searches your resume
**ATS match = {keyword_pct}% keyword match + {semantic_pct}% semantic match**

- **Keyword match:** the share of the job's ATS search terms (taken from its requirements) that appear in your
  resume. Matching is whole-term: "Java" never counts inside "JavaScript", while "REST API" matches "REST APIs".
  It updates live as you edit.
- **Semantic match:** each line of your resume is turned into an embedding (a numeric representation of its
  meaning) and compared with the job description; the five closest lines are averaged onto 0–100.
- Without a job description, the skills you enter are used for the keyword match instead.

### Reading your scores
- **Small changes (±2 points)** are shown as "about the same" — normal variation, not a real gain or loss.
- **Skills you don't have stay missing.** {APP_NAME} never adds experience to your resume on its own. If you
  genuinely have a missing skill, add it yourself from the Job match tab.
- **Scores differ between tools.** There is no official ATS score, and chat assistants often give generous
  estimates. Compare scores within {APP_NAME} (original vs. tailored, or job vs. job).
- The job's requirements are extracted once and reused, so the same job is judged against the same list. The list
  is only re-extracted when the app restarts, for example after an update.

### The {len(PIPELINE_STEPS)}-step AI pipeline
</div>
""", unsafe_allow_html=True)

st.markdown("\n".join(
    f"{i}. **{name}** — {description}" for i, (name, description) in enumerate(PIPELINE_STEPS, start=1)
))
