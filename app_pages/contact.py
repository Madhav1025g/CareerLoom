"""Contact: how to report a problem, suggest a feature, or get in touch."""
import streamlit as st

from main import APP_NAME
from ui_common import page_intro

REPO = "https://github.com/Madhav1025g/CareerLoom"

page_intro(
    "Contact",
    "Get in touch",
    f"Found a problem, have an idea, or want to talk about {APP_NAME}? Here's how to reach us.",
)

bug_col, idea_col, code_col = st.columns(3, gap="medium")
with bug_col, st.container(border=True, height="stretch"):
    st.markdown('<div class="cl-card-title">Report a problem</div>', unsafe_allow_html=True)
    st.caption("Something broken or a result that looks wrong? Tell us what happened and which page you were on. "
               "Please don't include your resume or personal details.")
    st.link_button("Report a problem", f"{REPO}/issues/new?labels=bug&title=Problem%3A%20",
                   icon=":material/bug_report:", width="stretch")
with idea_col, st.container(border=True, height="stretch"):
    st.markdown('<div class="cl-card-title">Suggest a feature</div>', unsafe_allow_html=True)
    st.caption(f"Ideas that would make {APP_NAME} more useful for your job search are always welcome.")
    st.link_button("Suggest a feature", f"{REPO}/issues/new?labels=enhancement&title=Idea%3A%20",
                   icon=":material/lightbulb:", width="stretch")
with code_col, st.container(border=True, height="stretch"):
    st.markdown('<div class="cl-card-title">See the code</div>', unsafe_allow_html=True)
    st.caption(f"{APP_NAME} is open source. Browse how it works, including how every score is calculated.")
    st.link_button("View on GitHub", REPO, icon=":material/code:", width="stretch")

st.write("")
st.caption("Reports and suggestions are posted publicly on GitHub (a free GitHub account is required). "
           "Quick feedback on your results? Use the thumbs up / down under “Your results”.")
