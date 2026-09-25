"""How we score: a plain-English explanation of the ATS score and the AI pipeline."""
import streamlit as st

from main import APP_NAME, KEYWORD_WEIGHT, PIPELINE_STEPS
from ui_common import page_intro

keyword_pct = round(KEYWORD_WEIGHT * 100)
semantic_pct = 100 - keyword_pct

page_intro(
    "How we score",
    "A transparent ATS score",
    f"{APP_NAME}'s ATS match score is a fixed formula, not an AI's opinion — so the same resume and job get the "
    "same score, and your original and tailored resumes are compared fairly.",
)

st.markdown(f"""
<div class="cl-prose">

### What the score measures
Applicant tracking systems (ATS) mostly help recruiters **search and filter resumes by keywords**. So the score
focuses on whether your resume contains the terms a recruiter for this job would search for.

**ATS match = {keyword_pct}% keyword match + {semantic_pct}% semantic match**

### 1. Keyword match ({keyword_pct}%)
- An AI reads the job description once and extracts its **10–20 most important hard requirements** — skills,
  tools, technologies, certifications, and domain terms, copied exactly as the job writes them.
- The score is the **share of those terms found in your resume**.
- Matching is whole-term and case-insensitive: "Java" does not count inside "JavaScript", while "REST API"
  matches "REST APIs".
- Your original and tailored resumes are checked against **the same list**, so the comparison is fair.
- The same job description always gets the same list — on every page (including Compare jobs) and every run.
- Without a job description, the skills you enter are used instead.

### 2. Semantic match ({semantic_pct}%)
- Each line of your resume is converted into an embedding (a numeric representation of its meaning) and compared
  with the job description.
- The five most similar lines are averaged and mapped onto 0–100.
- This rewards relevant experience even when it's worded differently from the job description.

### Reading your score
- **Small changes (±2 points)** are shown as "about the same" — that's normal variation, not a real gain or loss.
- **Skills you don't have stay missing.** {APP_NAME} never adds experience to your resume on its own. If you
  genuinely have a missing skill, add it yourself from the ATS analysis tab.
- **Scores differ between tools.** There is no official ATS score — every tool uses its own formula, and chat
  assistants often give generous estimates. Compare scores within {APP_NAME} (original vs. tailored, or job vs.
  job), not across tools. The keyword lists are the most actionable part.

### The {len(PIPELINE_STEPS)}-step AI pipeline
</div>
""", unsafe_allow_html=True)

st.markdown("\n".join(
    f"{i}. **{name}** — {description}" for i, (name, description) in enumerate(PIPELINE_STEPS, start=1)
))
