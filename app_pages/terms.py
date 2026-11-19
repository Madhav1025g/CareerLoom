"""Terms of use: plain-language rules for using CareerLoom."""
from datetime import date

import streamlit as st

from main import APP_NAME
from ui_common import page_intro

page_intro(
    "Terms of use",
    "The simple version",
    f"{APP_NAME} is a free tool that helps you tailor your own resume. By using it, you agree to these terms.",
)

st.markdown(f"""
<div class="cl-prose">

### Using {APP_NAME}
- {APP_NAME} is free and needs no account. To keep it available for everyone, the number of applications each
  session can generate is limited, and the service may be busy or unavailable at times.
- Only upload your own resume, or one you have permission to use. Don't upload other people's personal information
  without their consent.
- Don't use {APP_NAME} to create false or misleading applications, or try to overload, attack, or misuse the service.

### Your content and your results
- You keep all rights to your resume and to the documents {APP_NAME} generates for you.
- Results are produced by AI and can contain mistakes. **Review everything before you send it.** You are
  responsible for making sure your resume and cover letter are accurate and truthful.
- {APP_NAME} is designed not to invent experience, and it removes unsupported claims it detects, but no automated
  check is perfect.

### Scores and outcomes
- Requirement match and ATS match are estimates to help you improve your resume. They are not an official ATS
  score, and different employers' systems work differently.
- {APP_NAME} does not guarantee interviews, job offers, or any particular result.

### The service
- {APP_NAME} is provided "as is", without warranties of any kind. It may change, pause, or stop at any time.
- To the extent permitted by law, {APP_NAME} and its creator are not liable for any loss arising from use of the
  service or of the documents it generates.
- How your data is handled is described on the Privacy page.
- These terms may be updated. Changes take effect when they are posted here.

Last updated: {date(2026, 11, 19):%B %d, %Y}
</div>
""", unsafe_allow_html=True)
