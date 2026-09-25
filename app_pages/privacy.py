"""Privacy: exactly what happens to a user's data, matching what the code does."""
import streamlit as st

from main import APP_NAME
from ui_common import page_intro

page_intro(
    "Privacy",
    "Your resume stays yours",
    f"{APP_NAME} has no accounts and no resume database. Here is exactly what happens to your information.",
)

st.markdown(f"""
<div class="cl-prose">

### What we do with your resume
- **During your session:** your resume, job description, and results are kept in the app's memory so you can
  edit and download them. They are discarded when your session ends (for example, when you close the tab).
- **To generate results:** your resume and job description are sent to our AI provider,
  **Groq**, or **OpenAI** as a backup if Groq is unavailable.
- **For job matching:** lines of your resume are briefly stored as vectors in our **Qdrant** vector database to
  find the parts most relevant to the job. They are **deleted at the end of every request**.

### What we don't do
- We don't store your resume, job descriptions, or generated documents after your session.
- We don't write your resume or results into our logs. Logs contain only request IDs, processing steps, and scores.
- We don't sell or share your data, and we don't require an account or email address.

### Anonymous statistics
We count how many resumes are generated and how many people rate results as helpful or not helpful, using
counterapi.dev. These are plain numbers — no resume content or personal information is included.

### Third-party services
- **Groq** and **OpenAI** — AI text generation
- **Qdrant Cloud** — temporary vector search (deleted after each request)
- **Streamlit Community Cloud** — hosts this website
- **counterapi.dev** — anonymous usage counts
- **Google Fonts** — loads the website's typeface

### Questions
{APP_NAME} is an open-source project. You can review the code or ask a question on
[GitHub](https://github.com/Madhav1025g/CareerLoom).
</div>
""", unsafe_allow_html=True)
