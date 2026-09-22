from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, model_validator
from openai import OpenAI
from dotenv import load_dotenv
load_dotenv()  # Load environment variables from .env file
import json
import logging
import os
import re
import secrets
import time
import uuid

# Optional free LLM provider (Groq)
try:
    from groq import Groq
except ImportError:
    Groq = None

#----------------------
# APP Initialization
#----------------------

APP_NAME = "CareerLoom"

app = FastAPI(
    title=f"{APP_NAME} API",
    description="AI career document platform: tailored resumes, cover letters, and ATS match scoring with RAG-based job-description matching",
    version="3.0.0",
)

#----------------------
# SECURITY CONFIG
#----------------------

# Only non-empty keys count — an unset API_KEY_HERE must never let an empty key through.
valid_api_keys = {key for key in [os.getenv("API_KEY_HERE")] if key}
api_key_value = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=api_key_value) if api_key_value else None

# LLM provider selection — defaults to Groq (free) if configured, falls back to OpenAI
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "groq").lower()
groq_api_key = os.getenv("GROQ_API_KEY")
groq_client = Groq(api_key=groq_api_key) if (Groq and groq_api_key) else None

#----------------------
# RAG CONFIG
#----------------------

QDRANT_URL = os.getenv("QDRANT_URL")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")
COLLECTION_NAME = "resume_chunks"
EMBEDDING_DIM = 384  # all-MiniLM-L6-v2 output size

embedding_model = None
qdrant_client = None

# Only load the heavy embedding/vector libraries if Qdrant is actually configured.
if QDRANT_URL:
    from sentence_transformers import SentenceTransformer
    from qdrant_client import QdrantClient
    from qdrant_client.models import (
        Distance, VectorParams, PointStruct, Filter, FieldCondition, MatchValue, FilterSelector,
    )

    embedding_model = SentenceTransformer("all-MiniLM-L6-v2")
    qdrant_client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)
    existing_collections = [c.name for c in qdrant_client.get_collections().collections]
    if COLLECTION_NAME not in existing_collections:
        qdrant_client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(size=EMBEDDING_DIM, distance=Distance.COSINE),
        )

    # Qdrant requires a payload index to filter by a field (e.g. request_id).
    try:
        qdrant_client.create_payload_index(
            collection_name=COLLECTION_NAME,
            field_name="request_id",
            field_schema="keyword",
        )
    except Exception as exc:
        print(f"Payload index setup skipped (likely already exists): {exc}")

#----------------------
# REQUEST MODEL
#----------------------

class ResumeRequest(BaseModel):
    api_key: str
    full_name: str
    current_role: str
    skills: list[str]
    experience_years: int

    resume_text: str | None = Field(None, max_length=90000)
    resume_file: str | None = None   # File path or uploaded file name
    job_description: str | None = Field(None, max_length=20000)  # enables RAG matching

    @model_validator(mode="after")
    def validate_resume(self):
        # User must provide either resume text or a file
        if not self.resume_text and not self.resume_file:
            raise ValueError("Provide either resume text or upload a resume.")

        # Validate uploaded file type
        if self.resume_file:
            allowed = (".pdf", ".docx", ".txt")
            if not self.resume_file.lower().endswith(allowed):
                raise ValueError(
                    "Invalid file format. Only PDF, DOCX, and TXT are supported."
                )

        return self

#----------------------
# LOGGING CONFIG
#----------------------

# Logs go to stdout only (visible to the app owner in the hosting dashboard) — never to a file,
# and never into API responses. Do NOT pass resume text, prompts, LLM output, or keys to log_event.
logger = logging.getLogger("careerloom")
if not logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("[%(asctime)s] %(levelname)s %(message)s", "%Y-%m-%d %H:%M:%S"))
    logger.addHandler(_handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False


def log_event(message):
    logger.info(message)

#----------------------
# SECURITY VALIDATION
#----------------------

def verify_api_key(api_key):
    # Constant-time comparison; the key itself is never logged.
    if not any(secrets.compare_digest(api_key.encode(), valid.encode()) for valid in valid_api_keys):
        log_event("Rejected request with an invalid API key")
        raise HTTPException(status_code=401, detail="Invalid API Key")

#----------------------
# LLM HELPER
#----------------------

class LLMUnavailableError(RuntimeError):
    """Raised when no LLM provider could produce a response."""


def call_llm(prompt):
    # Groq path (free) — used when LLM_PROVIDER=groq and a key is configured
    if LLM_PROVIDER == "groq" and groq_client is not None:
        try:
            response = groq_client.chat.completions.create(
                model="openai/gpt-oss-20b",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=4096,
                temperature=0.4,
            )
            return response.choices[0].message.content
        except Exception as exc:
            log_event(f"Groq call failed ({type(exc).__name__}), falling back to OpenAI")

    if client is None:
        raise LLMUnavailableError("No LLM provider is configured or available.")

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            max_tokens=4096,
            temperature=0.4,
        )
        return response.choices[0].message.content
    except Exception as exc:
        log_event(f"OpenAI call failed ({type(exc).__name__})")
        raise LLMUnavailableError("All LLM providers failed.") from exc

#--------------------------------
# JSON PARSING HELPERS
#--------------------------------

def _extract_json(text, open_char, close_char):
    """Pull a JSON value out of LLM output, tolerating markdown fences or surrounding prose."""
    if not text:
        return None
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:]
    try:
        return json.loads(cleaned)
    except Exception:
        pass
    start, end = cleaned.find(open_char), cleaned.rfind(close_char)
    if start != -1 and end > start:
        try:
            return json.loads(cleaned[start:end + 1])
        except Exception:
            pass
    return None


def parse_json_list(text):
    """Safely parse a JSON array from LLM output."""
    data = _extract_json(text, "[", "]")
    return data if isinstance(data, list) else []


def parse_json_object(text):
    """Safely parse a JSON object from LLM output."""
    data = _extract_json(text, "{", "}")
    return data if isinstance(data, dict) else {}

#--------------------------------
# GUARDRAIL: COMPLETENESS CHECK
#--------------------------------

def extract_entry_markers(text: str) -> list[str]:
    """
    Heuristic: resume entries (jobs, projects) almost always have a date on the
    same line as the title/company. Extract those lines as a proxy for 'distinct entries'.
    """
    if not text:
        return []
    markers = []
    for line in text.split("\n"):
        if re.search(r"(19|20)\d{2}", line) and len(line.strip()) > 0:
            markers.append(line.strip())
    return markers


def check_completeness(original_text: str, final_text: str) -> dict:
    """
    Guardrail: compares year-marked lines (likely job/project headers) between the
    original resume and the AI-generated final version, to catch silently dropped entries.
    This is a heuristic safety net, not a guarantee — always encourage manual review.
    """
    original_markers = extract_entry_markers(original_text)
    final_text = final_text or ""

    missing = []
    for marker in original_markers:
        years_in_marker = re.findall(r"(?:19|20)\d{2}", marker)
        found = any(year in final_text for year in years_in_marker)
        if not found:
            missing.append(marker)

    total = len(original_markers)
    completeness_pct = 100 if total == 0 else round(100 * (total - len(missing)) / total)

    return {
        "completeness_pct": completeness_pct,
        "total_entries_detected": total,
        "possibly_missing": missing,
    }

#--------------------------------
# RAG HELPERS
#--------------------------------

def chunk_resume(resume_text: str) -> list[str]:
    """Split resume text into chunks (by line/bullet) for embedding."""
    if not resume_text:
        return []
    raw_lines = [line.strip() for line in resume_text.split("\n")]
    chunks = [line for line in raw_lines if len(line) > 15]  # drop empty/trivial lines
    return chunks


def embed_text(text: str) -> list[float]:
    if embedding_model is None:
        return []
    return embedding_model.encode(text).tolist()


def store_resume_chunks(request_id: str, chunks: list[str]):
    """Embed and upsert resume chunks into Qdrant, tagged with request_id."""
    if qdrant_client is None or not chunks:
        log_event("Qdrant not configured or no chunks to store — skipping vector storage")
        return

    points = []
    for chunk in chunks:
        vector = embed_text(chunk)
        points.append(
            PointStruct(
                id=str(uuid.uuid4()),
                vector=vector,
                payload={"request_id": request_id, "text": chunk},
            )
        )

    qdrant_client.upsert(collection_name=COLLECTION_NAME, points=points)
    log_event(f"{request_id}: stored {len(points)} resume chunks in Qdrant")


def delete_resume_chunks(request_id: str):
    """Remove this request's resume chunks from Qdrant so no resume content outlives the request."""
    if qdrant_client is None:
        return
    try:
        qdrant_client.delete(
            collection_name=COLLECTION_NAME,
            points_selector=FilterSelector(
                filter=Filter(must=[FieldCondition(key="request_id", match=MatchValue(value=request_id))])
            ),
        )
        log_event(f"{request_id}: deleted resume chunks from Qdrant")
    except Exception as exc:
        log_event(f"{request_id}: WARNING — failed to delete resume chunks ({type(exc).__name__})")


def retrieve_relevant_chunks(request_id: str, job_description: str, top_k: int = 5) -> list[str]:
    """Semantic search: find resume chunks most relevant to the job description."""
    if qdrant_client is None or not job_description:
        return []

    query_vector = embed_text(job_description)

    results = qdrant_client.query_points(
        collection_name=COLLECTION_NAME,
        query=query_vector,
        query_filter=Filter(
            must=[FieldCondition(key="request_id", match=MatchValue(value=request_id))]
        ),
        limit=top_k,
    )

    matched_chunks = [point.payload["text"] for point in results.points]
    log_event(f"{request_id}: retrieved {len(matched_chunks)} relevant chunks via vector search")
    return matched_chunks


def semantic_ats_score(job_description: str, matched_chunks: list[str]) -> int:
    """
    Similarity-based ATS score (0-100) using cosine similarity between the JD embedding
    and each matched chunk. Raw cosine similarity between a job description (long, formal)
    and a resume bullet (short, specific) rarely exceeds ~0.6 even for a strong match, so
    the raw value is rescaled here to map onto a more intuitive 0-100 "match quality" range.
    """
    if not job_description or not matched_chunks or embedding_model is None:
        return None

    jd_vector = embedding_model.encode(job_description)
    chunk_vectors = embedding_model.encode(matched_chunks)

    import numpy as np
    similarities = [
        float(np.dot(jd_vector, cv) / (np.linalg.norm(jd_vector) * np.linalg.norm(cv)))
        for cv in chunk_vectors
    ]
    avg_similarity = sum(similarities) / len(similarities)

    # Rescale: treat ~0.15 raw similarity as "0% match" and ~0.65 as "100% match" —
    # calibrated to this embedding model's typical range for JD-vs-resume-bullet comparisons.
    rescaled = (avg_similarity - 0.15) / (0.65 - 0.15) * 100
    score = round(rescaled)
    return max(0, min(score, 100))

#----------------------
# PROFILE ANALYZER AGENT
#----------------------

def analyzer_agent(user_request, request_id):

    log_event(f"{request_id}: Analyzer agent received request")

    prompt = f"""
    Analyze the following candidate profile.

    Name: {user_request['full_name']}
    Current Role: {user_request['current_role']}
    Skills: {', '.join(user_request['skills'])}
    Experience: {user_request['experience_years']} years

    Return ONLY JSON (no prose, no markdown fences):
    {{
      "candidate_level": "Entry Level" | "Mid-Level" | "Senior Level" | "Lead / Principal",
      "primary_domain": "short domain name, e.g. Backend Engineering",
      "years_experience": 0
    }}
    """

    output = call_llm(prompt)
    parsed = parse_json_object(output)

    log_event(f"{request_id}: Analyzer completed (parsed={bool(parsed)})")

    return {
        "candidate_level": parsed.get("candidate_level"),
        "primary_domain": parsed.get("primary_domain"),
        "years_experience": parsed.get("years_experience", user_request["experience_years"]),
    }

#----------------------
# ATS SCORE CALCULATOR
#----------------------

def calculate_ats_score(resume_text: str, skills: list[str]) -> int:
    if not resume_text:
        return 0

    score = 50
    lower_text = resume_text.lower()
    for skill in skills:
        # Match if every word in the skill appears somewhere in the resume
        # (handles "REST API" vs "RESTful APIs" style mismatches)
        skill_words = skill.lower().split()
        if skill_words and all(word in lower_text for word in skill_words):
            score += 10
        else:
            score -= 5

    return max(0, min(score, 100))

#------------------------
# ATS OPTIMIZATION AGENT (RAG-aware)
#------------------------

def ats_agent(user_request, matched_chunks=None, semantic_score=None):

    log_event("ATS Agent Started")

    # Blend keyword matching (literal, generous) with semantic similarity (conservative by nature —
    # raw cosine similarity between differently-styled texts rarely exceeds ~0.5-0.6 even for strong
    # matches, so using it alone makes even great resumes look artificially low).
    keyword_score = calculate_ats_score(user_request.get("resume_text", ""), user_request["skills"])
    if semantic_score is not None:
        final_score = round((keyword_score + semantic_score) / 2)
    else:
        final_score = keyword_score

    relevant_context = "\n".join(matched_chunks) if matched_chunks else user_request.get("resume_text", "")
    job_description = user_request.get("job_description")

    jd_section = (
        f"Job description to compare against:\n{job_description}"
        if job_description
        else "No job description was provided — just flag any obviously missing common skills relative to the candidate's stated skills list."
    )

    prompt = f"""
    Compare this resume content against the job description below (if provided) to identify
    specific tools, technologies, or experience the job asks for that are missing or barely
    represented in the resume.

    Resume content (most relevant excerpts):
    {relevant_context}

    Candidate's stated skills:
    {', '.join(user_request['skills'])}

    {jd_section}

    Return ONLY JSON (no prose, no markdown fences):
    {{
      "missing_keywords": [],
      "explanation": "one or two plain-English sentences explaining the main gaps holding the score back — name the specific missing tools/skills/experience. If nothing significant is missing, say the resume covers the job well."
    }}
    """

    output = call_llm(prompt)
    parsed = parse_json_object(output)
    missing_keywords = parsed.get("missing_keywords", []) if isinstance(parsed.get("missing_keywords"), list) else []
    explanation = parsed.get("explanation", "")

    log_event(f"ATS completed | keyword_score={keyword_score} semantic_score={semantic_score} final={final_score}")

    return {
        "llm_feedback": output,
        "ats_score": final_score,
        "keyword_score": keyword_score,
        "semantic_score": semantic_score,
        "missing_keywords": missing_keywords,
        "explanation": explanation,
    }

#----------------------
# SHARED OUTPUT FORMAT RULES
#----------------------

# The exporters (PDF/DOCX/preview) rely on this layout to produce a professionally formatted document.
RESUME_FORMAT_RULES = """
    Output format rules (follow exactly):
    - Output plain text only. Do NOT use Markdown: no **bold**, no # headings, no backticks.
    - Line 1: the candidate's full name only.
    - Line 2: contact details from the source (email, phone, location, links) separated by " | ". Omit if none are given.
    - Section headers on their own line in ALL CAPS (e.g. PROFESSIONAL SUMMARY, EXPERIENCE, PROJECTS, TECHNICAL SKILLS, EDUCATION, CERTIFICATIONS).
    - Each job or project starts with one header line containing the title, company/organization, location, and dates, separated by " | ".
    - Use plain bullet points starting with "- " for achievements. Never use tables, pipes-as-columns grids, or multi-column layouts.
    - Format TECHNICAL SKILLS as one category per line, e.g. "Languages: Python, JavaScript".
    """

#----------------------
# RESUME WRITER AGENT (uses RAG-matched content when available)
#----------------------

def resume_writer_agent(user_request, matched_chunks=None):

    log_event("Resume Writer Agent Started")

    full_resume_text = user_request.get("resume_text", "")

    emphasis_section = ""
    if matched_chunks:
        emphasis_section = f"""
    The following excerpts from the candidate's resume are especially relevant to this job —
    give them extra emphasis and prioritize them where natural, but this is guidance only:
    {chr(10).join(matched_chunks)}
    """

    prompt = f"""
    Generate a professional ATS-friendly resume.

    Name:
    {user_request['full_name']}

    Current Role:
    {user_request['current_role']}

    Skills:
    {', '.join(user_request['skills'])}

    Experience:
    {user_request['experience_years']} years

    Full source resume content (this is the complete and only source of truth — use ALL of it):
    {full_resume_text}
    {emphasis_section}
    {RESUME_FORMAT_RULES}
    - CRITICAL: Include every distinct job, company, and project mentioned in the full source content above,
      with their real company names and dates exactly as given. NEVER write placeholders like "[Not Provided]"
      or "[Company Name]" — if a detail is in the source text, use it verbatim; do not omit, merge, or
      genericize any entry, even if there are many.
    """

    resume = call_llm(prompt)

    output = {
        "generated_resume": resume
    }

    log_event("Resume generated successfully")

    return output


#----------------------
# HUMAN OPTIMIZER AGENT
#----------------------

def human_optimizer_agent(user_request, resume_text):

    log_event("Human Optimizer Agent Started")

    prompt = f"""
    Rewrite the resume below.

    Make it:

    - Natural
    - Human sounding
    - Remove AI generated patterns
    - Professional
    - ATS Friendly
    {RESUME_FORMAT_RULES}
    - CRITICAL: Preserve every distinct job, company, and project entry from the resume below.
      Do not drop, merge, or summarize away any entry while rewriting — the output must contain
      the exact same number of jobs/projects as the input, just better-written.

    Resume:

    {resume_text}
    """

    optimized_resume = call_llm(prompt)

    output = {
        "human_friendly_resume": optimized_resume
    }

    log_event("Human optimization completed")

    return output

#----------------------
# REVIEWER AGENT (reviews the FINAL resume, returns structured suggestions)
#----------------------

def reviewer_agent(resume_text):

    log_event("Reviewer Agent Started")

    prompt = f"""
    Review this resume for grammar, formatting, professionalism, and consistency.

    Resume:

    {resume_text}

    Return ONLY a JSON array (no prose, no markdown code fences) where each item has:
    - "issue": a short category label (e.g. "Grammar", "Formatting", "Consistency")
    - "current_text": the exact snippet from the resume above with the issue, copied verbatim
    - "suggested_fix": the corrected version of that exact snippet

    CRITICAL: Only include an item if suggested_fix is genuinely different from current_text and
    is non-empty. Do NOT include an item just to reach a quota — if current_text and suggested_fix
    would be identical, or if you have nothing meaningful to suggest, leave that item out entirely.

    Return at most 8 of the most impactful items. If there are no real issues, return [].
    """

    raw_output = call_llm(prompt)
    suggestions = parse_json_list(raw_output)

    # Safety net: drop any no-op or empty suggestions even if the model ignored the instruction above
    suggestions = [
        s for s in suggestions
        if isinstance(s, dict)
        and str(s.get("suggested_fix", "")).strip()
        and str(s.get("suggested_fix", "")).strip() != str(s.get("current_text", "")).strip()
    ]

    log_event(f"Reviewer completed with {len(suggestions)} suggestions")

    return {
        "review_feedback": raw_output,
        "suggestions": suggestions,
    }

#----------------------
# COVER LETTER AGENT
#----------------------

def cover_letter_agent(user_request, matched_chunks=None):

    log_event("Cover Letter Agent Started")

    job_description = user_request.get("job_description") or ""
    relevant_context = "\n".join(matched_chunks) if matched_chunks else user_request.get("resume_text", "")

    if job_description:
        jd_instruction = f"Tailor it specifically to this job description:\n{job_description}"
    else:
        jd_instruction = "No specific job description was provided — write a strong, general-purpose cover letter highlighting the candidate's background."

    prompt = f"""
    Write a professional, concise cover letter (3-4 short paragraphs) for the candidate below.

    Candidate Name: {user_request['full_name']}
    Current Role: {user_request['current_role']}
    Years of Experience: {user_request['experience_years']}
    Key Skills: {', '.join(user_request['skills'])}

    Most relevant experience from their resume:
    {relevant_context}

    {jd_instruction}

    Write in first person, professional but not stiff. If no company name is given, address it "Dear Hiring Manager,". Do not include placeholder brackets like [Company Name] unless a real company name was provided in the job description.
    Output plain text only (no Markdown). Start with the salutation and end with "Sincerely," followed by the candidate's name on the next line. Separate paragraphs with a blank line.
    """

    letter = call_llm(prompt)

    output = {
        "cover_letter": letter
    }

    log_event("Cover letter generated successfully")

    return output

#----------------------
# ORCHESTRATOR (RAG step, 7-step pipeline, progress callback)
#----------------------

PIPELINE_STEPS = [
    ("Profile Analyzer", "Reads your background and determines your experience level and domain."),
    ("ATS Match", "Scores your resume against the job using semantic (RAG) and keyword matching."),
    ("Resume Writer", "Drafts a tailored resume using your full resume as the only source of truth."),
    ("Human Optimizer", "Polishes the draft so it reads naturally, not like AI-generated text."),
    ("Completeness Check", "A guardrail that flags any job or project that may have been dropped."),
    ("Reviewer", "Checks grammar, formatting, and consistency, with one-click fixes."),
    ("Cover Letter Writer", "Drafts a matching cover letter tailored to the same role."),
]


def orchestrator(user_request, request_id, progress_callback=None):
    log_event(f"{request_id}: Orchestrator started")
    start = time.time()

    def notify(message):
        log_event(f"{request_id}: {message}")
        if progress_callback:
            progress_callback(message)

    # RAG step — chunk + store resume, then retrieve JD-relevant chunks
    matched_chunks = []
    semantic_score = None
    resume_text = user_request.get("resume_text")
    job_description = user_request.get("job_description")

    try:
        notify("Reading your resume...")
        if resume_text:
            chunks = chunk_resume(resume_text)
            store_resume_chunks(request_id, chunks)

            if job_description:
                notify("Matching your resume to the job description...")
                matched_chunks = retrieve_relevant_chunks(request_id, job_description)
                semantic_score = semantic_ats_score(job_description, matched_chunks)
    finally:
        # Resume chunks are only needed for retrieval — never keep them beyond this request.
        delete_resume_chunks(request_id)

    notify("Analyzing your profile...")
    analyzer_output = analyzer_agent(user_request, request_id)

    notify("Scoring your ATS match...")
    ats_output = ats_agent(user_request, matched_chunks=matched_chunks, semantic_score=semantic_score)

    notify("Writing your tailored resume...")
    resume_writer_output = resume_writer_agent(user_request, matched_chunks=matched_chunks)

    notify("Polishing the final version...")
    human_optimizer_output = human_optimizer_agent(user_request, resume_writer_output["generated_resume"])

    notify("Checking that nothing was dropped...")
    final_resume_text = human_optimizer_output["human_friendly_resume"]
    completeness_output = check_completeness(resume_text, final_resume_text)
    if completeness_output["possibly_missing"]:
        log_event(f"{request_id}: WARNING — {len(completeness_output['possibly_missing'])} entries possibly dropped")

    notify("Reviewing grammar and consistency...")
    reviewer_output = reviewer_agent(final_resume_text)

    notify("Drafting your cover letter...")
    cover_letter_output = cover_letter_agent(user_request, matched_chunks=matched_chunks)

    execution_time = round(time.time() - start, 2)
    log_event(f"{request_id}: Orchestrator finished in {execution_time}s")

    return {
        "status": "success",
        "request_id": request_id,
        "execution_time": execution_time,
        "rag_matches_used": len(matched_chunks),
        "workflow": {
            "analyzer": analyzer_output,
            "ats_optimization": ats_output,
            "resume_writer": resume_writer_output,
            "human_optimizer": human_optimizer_output,
            "reviewer": reviewer_output,
            "cover_letter": cover_letter_output,
            "completeness_check": completeness_output,
        },
    }

#----------------------
# ROOT ENDPOINT
#----------------------
@app.get("/")
def home():
    return {"message": f"Welcome to the {APP_NAME} API!"}

#----------------------
# MAIN API ENDPOINT
#----------------------
@app.post("/generate_resume")
def generate_resume(request: ResumeRequest):
    request_id = str(uuid.uuid4())

    # SECURITY CHECK
    verify_api_key(request.api_key)

    # WORKFLOW EXECUTION
    try:
        return orchestrator(request.model_dump(), request_id)
    except LLMUnavailableError:
        raise HTTPException(status_code=503, detail="The AI service is temporarily unavailable. Please try again shortly.")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
