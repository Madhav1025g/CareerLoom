"""Shared styling, layout pieces, and helpers used by every CareerLoom page."""
import html
import re

import requests
import streamlit as st

from main import APP_NAME

CSS = """<style>
.block-container { max-width: 1140px; padding-top: 2.2rem; padding-bottom: 3rem; }
/* Top navigation bar: solid so page content never shows through it while scrolling */
header[data-testid="stHeader"] { background: rgba(255, 255, 255, 0.97); border-bottom: 1px solid #E3E7EF;
                                 backdrop-filter: blur(6px); }

.cl-nav { display: flex; align-items: center; justify-content: space-between; margin-bottom: 2.4rem; }
.cl-brand { display: flex; align-items: center; gap: 0.6rem; font-weight: 700; font-size: 1.25rem; color: #0F172A; letter-spacing: -0.01em; }
.cl-mark { display: inline-flex; align-items: center; justify-content: center; width: 34px; height: 34px;
           border-radius: 8px; background: #1E3A8A; color: #fff; font-size: 0.85rem; font-weight: 700; }
.cl-mark span { color: #F59E0B; }
.cl-pill { font-size: 0.78rem; font-weight: 600; color: #1E3A8A; background: #EEF2FF; border: 1px solid #DCE3F9;
           padding: 0.3rem 0.75rem; border-radius: 999px; }

.cl-hero { padding: 0.5rem 0 1.8rem 0; max-width: 780px; }
.cl-eyebrow { text-transform: uppercase; letter-spacing: 0.12em; font-size: 0.75rem; font-weight: 700; color: #B45309; margin-bottom: 0.7rem; }
.cl-h1 { font-size: 2.6rem; line-height: 1.12; font-weight: 700; color: #0F172A; letter-spacing: -0.025em; margin-bottom: 0.9rem; }
.cl-lead { font-size: 1.08rem; line-height: 1.6; color: #475569; }

.cl-features { display: grid; grid-template-columns: repeat(auto-fit, minmax(230px, 1fr)); gap: 1rem; margin-bottom: 2.6rem; }
.cl-feature { border: 1px solid #E3E7EF; border-radius: 12px; padding: 1.1rem 1.2rem; background: #FAFBFD; }
.cl-feature-title { font-weight: 600; color: #0F172A; margin-bottom: 0.3rem; }
.cl-feature-text { font-size: 0.9rem; color: #64748B; line-height: 1.5; }

.cl-section-title { font-size: 1.45rem; font-weight: 700; color: #0F172A; letter-spacing: -0.015em; margin: 0.4rem 0 0.2rem 0; }
.cl-section-sub { color: #64748B; font-size: 0.95rem; margin-bottom: 1rem; }
.cl-card-title { font-weight: 600; font-size: 1rem; color: #0F172A; margin-bottom: 0.2rem; }
.cl-privacy { font-size: 0.82rem; color: #64748B; text-align: center; margin-top: 0.6rem; }

/* Document preview — template values arrive as CSS variables from document_builder */
.cl-doc { background: #fff; border: 1px solid #E3E7EF; border-radius: 10px; padding: 2.2rem 2.5rem;
          box-shadow: 0 1px 3px rgba(15,23,42,.05), 0 10px 30px rgba(15,23,42,.06);
          color: #111827; font-size: var(--doc-size, 0.9rem); line-height: 1.5; max-height: 1000px; overflow-y: auto; }
.cl-doc, .cl-doc * { font-family: var(--doc-font, Inter, sans-serif) !important; }
.cl-doc p { margin: 0.12rem 0 !important; font-size: var(--doc-size, 0.9rem) !important; }
.cl-doc ul { margin: 0.15rem 0 0.35rem 1.1rem !important; padding: 0 !important; }
.cl-doc li { margin: 0.08rem 0 !important; font-size: var(--doc-size, 0.9rem) !important; }
.cl-name { text-align: var(--doc-align, center); font-size: 1.6rem; font-weight: 700; color: var(--doc-accent, #1E3A8A); letter-spacing: -0.01em; }
.cl-contact { text-align: var(--doc-align, center); color: #64748B; font-size: 0.8rem; margin-top: 0.15rem; }
.cl-heading { margin: 1.1rem 0 0.45rem 0; color: var(--doc-accent, #1E3A8A); font-weight: 700; font-size: 0.8rem; letter-spacing: 0.08em; }
.cl-heading-rule { padding-bottom: 0.2rem; border-bottom: 1.5px solid var(--doc-accent, #1E3A8A); }
.cl-heading-bar { padding-left: 0.55rem; border-left: 3px solid var(--doc-accent, #1E3A8A); }
.cl-entry { font-weight: 600; margin-top: 0.55rem; }
[data-testid="stMetricValue"] { font-size: 1.9rem; }
.cl-letter { padding: 2.6rem 3rem; }
.cl-letter p { margin: 0 0 0.9rem 0 !important; }

.cl-chips { display: flex; flex-wrap: wrap; gap: 0.4rem; margin: 0.4rem 0 1rem 0; }
.cl-chip { font-size: 0.8rem; font-weight: 500; color: #9A3412; background: #FFF7ED; border: 1px solid #FED7AA;
           border-radius: 999px; padding: 0.2rem 0.65rem; }
.cl-chip-good { color: #166534; background: #F0FDF4; border-color: #BBF7D0; }
.cl-hero-sm { padding: 0.2rem 0 1.4rem 0; }
.cl-hero-sm .cl-h1 { font-size: 2.1rem; }
.cl-footer-rule { border-top: 1px solid #E3E7EF; margin-top: 3rem; padding-top: 0.6rem; }
.cl-rank { display: inline-flex; align-items: center; justify-content: center; width: 26px; height: 26px; border-radius: 999px;
           background: #1E3A8A; color: #fff; font-weight: 700; font-size: 0.85rem; margin-right: 0.5rem; }
.cl-prose { max-width: 780px; color: #334155; line-height: 1.65; }
.cl-prose h3 { color: #0F172A; margin-top: 1.6rem; }

.cl-footer { border-top: 1px solid #E3E7EF; margin-top: 3rem; padding-top: 1.2rem; color: #94A3B8; font-size: 0.82rem;
             display: flex; justify-content: space-between; flex-wrap: wrap; gap: 0.5rem; }
</style>
"""


def apply_styles():
    st.markdown(CSS, unsafe_allow_html=True)

# ------------------------------------------------------------------
# Anonymous usage counters (owner analytics only — counts, never content)
# ------------------------------------------------------------------
COUNTER_NAMESPACE = "ai-resume-generator-demo"


def _bump(counter_key: str):
    try:
        requests.get(f"https://api.counterapi.dev/v1/{COUNTER_NAMESPACE}/{counter_key}/up", timeout=3)
    except Exception:
        pass


def increment_counter():
    _bump("resumes-generated")


def record_feedback(helpful: bool):
    _bump("feedback-helpful" if helpful else "feedback-not-helpful")

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


def chips(keywords, extra_class=""):
    items = "".join(f'<span class="cl-chip {extra_class}">{html.escape(str(k))}</span>' for k in keywords)
    st.markdown(f'<div class="cl-chips">{items}</div>', unsafe_allow_html=True)


def busy_message(exc) -> str:
    when = "later today" if getattr(exc, "daily", False) else "in a few minutes"
    return (f"{APP_NAME} is very busy right now — our free AI capacity is used up for the moment. "
            f"Please try again {when}. This attempt didn't count toward your limit.")


def page_intro(eyebrow: str, title: str, lead: str):
    st.markdown(f'''<div class="cl-hero cl-hero-sm"><div class="cl-eyebrow">{eyebrow}</div>
<div class="cl-h1">{title}</div><div class="cl-lead">{lead}</div></div>''', unsafe_allow_html=True)
