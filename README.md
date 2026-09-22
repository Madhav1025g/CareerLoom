# CareerLoom

**AI career document platform: tailored resumes, cover letters, and ATS match scoring.**

**Live app:** https://airesumegeneratoragent.streamlit.app/

CareerLoom reads your resume and a job description, then generates a tailored resume, a matching cover letter, and an ATS match score with a clear gap analysis, all in one pass.

## Features

- Upload your resume (PDF, DOCX, or TXT) or paste it directly
- Paste a job description for semantically matched, tailored output
- ATS match score (semantic + keyword) with missing skills and a plain-English explanation
- Rewritten, ATS-friendly resume plus a matching cover letter
- Reviewer suggestions with one-click **Apply**
- Professionally formatted **PDF** and **Word** exports, plus plain text

## How it works

A 7-step multi-agent pipeline:

1. **Profile Analyzer**: determines experience level and domain
2. **ATS Match**: scores the resume against the job using RAG-based semantic matching plus keyword matching
3. **Resume Writer**: drafts a tailored resume using the full resume as the only source of truth
4. **Human Optimizer**: polishes the draft so it reads naturally
5. **Completeness Check**: a guardrail that flags any job or project that may have been dropped
6. **Reviewer**: checks grammar, formatting, and consistency, returning applicable fixes
7. **Cover Letter Writer**: drafts a matching cover letter

Job-description matching uses a **RAG pipeline** (Sentence-Transformers embeddings + Qdrant vector search).

## Privacy

- Resume content is sent to the LLM provider only to generate results.
- Resume chunks stored in Qdrant for matching are **deleted at the end of every request**.
- Application logs contain only request IDs, pipeline steps, and scores. They never contain resume text, prompts, or API keys, and they are never written to files.

## Tech stack

| Layer | Tools |
|---|---|
| Backend | Python, FastAPI, Pydantic |
| AI / LLM | Groq (primary), OpenAI (fallback), Sentence-Transformers, Qdrant |
| Frontend | Streamlit |
| Documents | pypdf, python-docx, fpdf2 |
| Deployment | Streamlit Community Cloud |

## Project structure

```
streamlit_app.py      # Web UI
main.py               # Agents, orchestrator, RAG, and FastAPI endpoint
document_builder.py   # Resume/cover letter formatting for preview, PDF, and DOCX
.streamlit/config.toml  # Theme
assets/               # Favicon
```

## Running locally

```bash
git clone https://github.com/Madhav1025g/Enterprise_AI_Resume_Generator_Agent.git
cd Enterprise_AI_Resume_Generator_Agent
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

Create a `.env` file (never commit it; it is in `.gitignore`):

```
GROQ_API_KEY=your_groq_key
OPENAI_API_KEY=optional_openai_fallback_key
QDRANT_URL=your_qdrant_cluster_url
QDRANT_API_KEY=your_qdrant_api_key
LLM_PROVIDER=groq
API_KEY_HERE=a_long_random_value   # protects the FastAPI endpoint
```

Run the web app:

```bash
streamlit run streamlit_app.py
```

Or run the REST API (docs at http://127.0.0.1:8000/docs):

```bash
uvicorn main:app --reload
```

## Author

Built by Madhav G
