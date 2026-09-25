"""CareerLoom entry point: secrets, page config, top navigation, and the shared footer."""
import os
from datetime import date

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

from main import APP_NAME  # noqa: E402  (must import after secrets are in the environment)
from ui_common import apply_styles  # noqa: E402

st.set_page_config(page_title=f"{APP_NAME} | AI Resume Tailoring", page_icon="assets/favicon.png", layout="wide")
st.logo("assets/logo.png", size="large")
apply_styles()

# Streamlit forgets a widget's value when you visit a page without that widget. Re-assigning these keys
# on every run keeps the form filled in while users move between pages.
PERSISTENT_KEYS = ["full_name", "current_role", "skills_input", "experience_years",
                   "resume_text_area", "job_description_area", "template"]
for key in PERSISTENT_KEYS:
    if key in st.session_state:
        st.session_state[key] = st.session_state[key]

tailor_page = st.Page("app_pages/tailor.py", title="Tailor resume", icon=":material/description:", default=True)
compare_page = st.Page("app_pages/compare.py", title="Compare jobs", icon=":material/compare_arrows:", url_path="compare")
score_page = st.Page("app_pages/how_we_score.py", title="How we score", icon=":material/analytics:", url_path="how-we-score")
privacy_page = st.Page("app_pages/privacy.py", title="Privacy", icon=":material/lock:", url_path="privacy")
st.session_state.pages = {"tailor": tailor_page, "compare": compare_page}

st.navigation([tailor_page, compare_page, score_page, privacy_page], position="top").run()

# ------------------------------------------------------------------
# Footer (st.page_link keeps the session — plain <a> links would reload the app and lose results)
# ------------------------------------------------------------------
st.markdown('<div class="cl-footer-rule"></div>', unsafe_allow_html=True)
copy_col, *link_cols = st.columns([4, 1.2, 1.2, 1.2], vertical_alignment="center")
copy_col.caption(f"© {date.today().year} {APP_NAME}. Built by Madhav G. "
                 "Your data is processed only to generate your results and is never stored.")
for col, page in zip(link_cols, [compare_page, score_page, privacy_page]):
    col.page_link(page)
