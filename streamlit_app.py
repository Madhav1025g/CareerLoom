"""CareerLoom entry point: secrets, page config, top navigation, and the shared footer."""
import os
from datetime import date

import streamlit as st

# ------------------------------------------------------------------
# Load secrets (API keys) from Streamlit Cloud's secrets manager.
# Locally there may be no secrets.toml — main.py falls back to .env.
# ------------------------------------------------------------------
try:
    for key in ["OPENAI_API_KEY", "GROQ_API_KEY", "LLM_PROVIDER", "API_KEY_HERE"]:
        if key in st.secrets:
            os.environ[key] = st.secrets[key]
except Exception:
    pass

from main import APP_NAME, preload_embedding_model  # noqa: E402  (must import after secrets are in the environment)
from ui_common import apply_styles, is_dark_theme  # noqa: E402

st.set_page_config(page_title=f"{APP_NAME} | AI Resume Tailoring", page_icon="assets/favicon.png", layout="wide")
st.logo("assets/logo_dark.png" if is_dark_theme() else "assets/logo.png", size="large")
apply_styles()


@st.cache_resource(show_spinner=False)
def _start_model_preload():
    preload_embedding_model()  # once per server process: the first generation doesn't wait for the model
    return True


_start_model_preload()

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
terms_page = st.Page("app_pages/terms.py", title="Terms of use", icon=":material/gavel:", url_path="terms")
contact_page = st.Page("app_pages/contact.py", title="Contact", icon=":material/mail:", url_path="contact")
st.session_state.pages = {"tailor": tailor_page, "compare": compare_page}

# Main pages sit in the top bar; the legal and contact pages are grouped under "About" (a dropdown in the top bar).
st.navigation({"": [tailor_page, compare_page, score_page], "About": [privacy_page, terms_page, contact_page]},
              position="top").run()

# ------------------------------------------------------------------
# Footer (st.page_link keeps the session — plain <a> links would reload the app and lose results)
# ------------------------------------------------------------------
st.markdown('<div class="cl-footer-rule"></div>', unsafe_allow_html=True)
copy_col, links_col = st.columns([4, 5], vertical_alignment="center")
copy_col.caption(f"© {date.today().year} {APP_NAME}. Built by Madhav G. "
                 "Your data is processed only to generate your results and is never stored.")
with links_col.container(horizontal=True, horizontal_alignment="right", gap="small"):
    for page in [score_page, privacy_page, terms_page, contact_page]:
        st.page_link(page, width="content")
