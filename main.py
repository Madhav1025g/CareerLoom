from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, model_validator
from openai import OpenAI
from dotenv import load_dotenv
load_dotenv()  # Load environment variables from .env file
from concurrent.futures import ThreadPoolExecutor
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
# Several agents run in parallel, so allow extra retries — the SDK backs off automatically on rate limits (429).
groq_client = Groq(api_key=groq_api_key, max_retries=4) if (Groq and groq_api_key) else None

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
            # gpt-oss is a reasoning model: hidden reasoning tokens count against max_tokens. Low effort
            # leaves room for the actual resume; max_tokens stays small enough for Groq's free-tier TPM limit.
            response = groq_client.chat.completions.create(
                model="openai/gpt-oss-20b",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=4096,
                temperature=0.4,
                reasoning_effort="low",
            )
            choice = response.choices[0]
            content = (choice.message.content or "").strip()
            if choice.finish_reason == "length":
                log_event("Groq output hit the token limit and may be truncated")
            if content:
                return content
            log_event("Groq returned an empty response, falling back to OpenAI")
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
        content = (response.choices[0].message.content or "").strip()
    except Exception as exc:
        log_event(f"OpenAI call failed ({type(exc).__name__})")
        raise LLMUnavailableError("All LLM providers failed.") from exc
    if not content:
        raise LLMUnavailableError("The LLM returned an empty response.")
    return content

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
        # All of an entry's years must survive — "any" let a dropped 2019-2020 job hide behind a 2019 degree.
        years_in_marker = re.findall(r"(?:19|20)\d{2}", marker)
        found = all(year in final_text for year in years_in_marker)
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


def semantic_ats_score(job_description: str, chunks: list[str], top_k: int = 5) -> int:
    """
    Similarity-based ATS score (0-100): the average cosine similarity between the JD embedding
    and the top_k most similar resume chunks. Raw cosine similarity between a job description
    (long, formal) and a resume bullet (short, specific) rarely exceeds ~0.6 even for a strong
    match, so the raw value is rescaled onto a more intuitive 0-100 "match quality" range.
    """
    if not job_description or not chunks or embedding_model is None:
        return None

    jd_vector = embedding_model.encode(job_description)
    chunk_vectors = embedding_model.encode(chunks)

    import numpy as np
    similarities = sorted(
        (float(np.dot(jd_vector, cv) / (np.linalg.norm(jd_vector) * np.linalg.norm(cv))) for cv in chunk_vectors),
        reverse=True,
    )[:top_k]
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


def contains_term(text: str, term: str) -> bool:
    """
    Whole-term, case-insensitive match: "Java" does not match inside "JavaScript", while
    "REST API" matches "REST APIs" and "CI/CD" matches "CI/CD pipelines".
    """
    term = (term or "").strip().lower()
    if not term or not text:
        return False
    variants = {term, term[:-1] if term.endswith("s") else term + "s"}
    lower = text.lower()
    return any(re.search(r"(?<![a-z0-9])" + re.escape(v) + r"(?![a-z0-9])", lower) for v in variants if v)


def keyword_coverage(resume_text: str, job_keywords: list[str]) -> dict:
    """Which of the job's key terms appear in the resume — what real ATS systems mostly check."""
    covered = [k for k in job_keywords if contains_term(resume_text, k)]
    missing = [k for k in job_keywords if k not in covered]
    score = round(100 * len(covered) / len(job_keywords)) if job_keywords else None
    return {"score": score, "covered": covered, "missing": missing}


# Real ATS systems are keyword-driven, so keyword coverage carries more weight than semantic similarity
# (which also moves a few points from wording alone).
KEYWORD_WEIGHT = 0.6


def ats_breakdown(resume_text: str, job_description: str | None, skills: list[str],
                  job_keywords: list[str] | None = None) -> dict:
    """
    Score any resume text the same way, so the original and tailored versions are comparable.
    Keyword score = coverage of the job's key terms (falls back to the candidate's stated skills
    when no job keywords are available); semantic score = embedding similarity to the job description.
    """
    coverage = keyword_coverage(resume_text, job_keywords or [])
    keyword_score = coverage["score"] if coverage["score"] is not None else calculate_ats_score(resume_text, skills)
    semantic_score = semantic_ats_score(job_description, chunk_resume(resume_text))
    if semantic_score is None:
        overall = keyword_score
    else:
        overall = round(KEYWORD_WEIGHT * keyword_score + (1 - KEYWORD_WEIGHT) * semantic_score)
    return {"overall": overall, "keyword": keyword_score, "semantic": semantic_score,
            "covered": coverage["covered"], "missing": coverage["missing"]}

#------------------------
# ATS OPTIMIZATION AGENT (RAG-aware)
#------------------------

def ats_agent(user_request, matched_chunks=None):
    """
    Extracts the job's key terms ONCE, so the original and tailored resumes are scored against the
    same list. Which terms are covered or missing is then computed deterministically, not guessed.
    """

    log_event("ATS Agent Started")

    resume_text = user_request.get("resume_text") or ""
    job_description = (user_request.get("job_description") or "").strip()

    if job_description:
        task = f"""
    1. "job_keywords": the 10-20 most important hard requirements in the job description below — skills, tools,
       technologies, platforms, methodologies, certifications, and domain terms. Copy each term exactly as the
       job description writes it, keep each to 1-4 words, and exclude soft skills (e.g. "team player").
    2. "explanation": one or two plain-English sentences on the main gaps between the resume and the job,
       naming specific missing tools/skills. If nothing significant is missing, say the resume covers the job well.

    Job description:
    {job_description[:JD_PROMPT_CHARS]}
    """
    else:
        task = """
    No job description was provided. Return "job_keywords": [] and an "explanation" naming any obviously
    missing common skills relative to the candidate's stated skills and role.
    """

    prompt = f"""
    You are an ATS (applicant tracking system) analyst. Produce:
    {task}
    Candidate's full resume:
    {resume_text}

    Candidate's stated skills: {', '.join(user_request['skills'])}

    Return ONLY JSON (no prose, no markdown fences):
    {{"job_keywords": [], "explanation": ""}}
    """

    output = call_llm(prompt)
    parsed = parse_json_object(output)
    raw_keywords = parsed.get("job_keywords") if isinstance(parsed.get("job_keywords"), list) else []
    job_keywords = list(dict.fromkeys(str(k).strip() for k in raw_keywords if str(k).strip()))[:20]
    explanation = parsed.get("explanation", "")

    scores = ats_breakdown(resume_text, job_description or None, user_request["skills"], job_keywords)
    log_event(f"ATS completed | keywords={len(job_keywords)} keyword_score={scores['keyword']} "
              f"semantic_score={scores['semantic']} final={scores['overall']}")

    return {
        "llm_feedback": output,
        "ats_score": scores["overall"],
        "keyword_score": scores["keyword"],
        "semantic_score": scores["semantic"],
        "job_keywords": job_keywords,
        "covered_keywords": scores["covered"],
        "missing_keywords": scores["missing"],
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
# GUARDRAIL: USABLE OUTPUT CHECK
#----------------------

class ResumeGenerationError(RuntimeError):
    """Raised when the LLM keeps returning something that isn't a resume (empty, truncated, or a question)."""


_NON_RESUME_PHRASES = (
    "please paste", "please provide", "please share", "i need the", "i'm ready to", "i am ready to",
    "could you provide", "could you share", "i can't", "i cannot", "as an ai",
)


def is_usable_resume(text: str, source_text: str | None) -> bool:
    """Reject empty, suspiciously short, or conversational LLM replies before they reach the user."""
    if not text or len(text.strip()) < 200:
        return False
    opening = text.strip()[:250].lower()
    if any(phrase in opening for phrase in _NON_RESUME_PHRASES):
        return False
    if source_text and len(text) < 0.3 * len(source_text):
        return False
    return True

#----------------------
# RESUME WRITER AGENT (uses RAG-matched content when available)
#----------------------

JD_PROMPT_CHARS = 4000  # keeps prompts within Groq's free-tier tokens-per-minute limit


def tailoring_section(user_request, missing_keywords=None, covered_keywords=None) -> str:
    """Job-targeting instructions shared by the writer and optimizer, with strict no-fabrication rules."""
    job_description = (user_request.get("job_description") or "").strip()
    if not job_description:
        return f"""
    No job description was given — tailor the resume to a {user_request['current_role'] or 'role matching the candidate'} position.
    """
    gaps = ", ".join(map(str, missing_keywords or [])) or "none identified"
    keep = ", ".join(map(str, covered_keywords or [])) or "none identified"
    return f"""
    TARGET JOB DESCRIPTION (tailor the resume to THIS role):
    {job_description[:JD_PROMPT_CHARS]}

    Job keywords the original resume ALREADY contains — every one MUST appear, spelled exactly like this: {keep}
    Job keywords the original resume is missing: {gaps}

    Tailoring rules:
    - Open the PROFESSIONAL SUMMARY with the target role's title and the candidate's strengths most relevant to it.
    - Mirror the job description's exact terminology wherever the candidate's real experience matches
      (e.g. if the job says "CI/CD" and the resume says "automated deployments", write "CI/CD (automated deployments)").
    - Within each job, put the most job-relevant bullets first. Order skill categories by relevance to the job.
    - For each missing keyword: include it ONLY if the source resume shows the candidate genuinely has
      that experience, possibly under different wording. NEVER add a skill, tool, certification, employer, title,
      or metric that the source resume does not support. Honesty matters more than the score.
    """


def resume_writer_agent(user_request, matched_chunks=None, missing_keywords=None, covered_keywords=None):

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
    {tailoring_section(user_request, missing_keywords, covered_keywords)}
    {RESUME_FORMAT_RULES}
    - CRITICAL: Include every distinct job, company, and project mentioned in the full source content above,
      with their real company names and dates exactly as given. NEVER write placeholders like "[Not Provided]"
      or "[Company Name]" — if a detail is in the source text, use it verbatim; do not omit, merge, or
      genericize any entry, even if there are many.
    """

    resume = call_llm(prompt)
    if not is_usable_resume(resume, full_resume_text):
        log_event("Resume Writer output unusable — retrying once")
        resume = call_llm(prompt)
        if not is_usable_resume(resume, full_resume_text):
            raise ResumeGenerationError("The resume writer did not return a complete resume.")

    output = {
        "generated_resume": resume
    }

    log_event("Resume generated successfully")

    return output


#----------------------
# HUMAN OPTIMIZER AGENT
#----------------------

def human_optimizer_agent(user_request, resume_text, keep_keywords=None):

    log_event("Human Optimizer Agent Started")

    prompt = f"""
    Rewrite the resume below.

    Make it:

    - Natural
    - Human sounding
    - Remove AI generated patterns
    - Professional
    - ATS Friendly

    This resume has been tailored to the job below. Keep that tailoring: preserve every job-description
    keyword and specific technical term — never swap them for generic synonyms — and keep the most
    job-relevant bullets first. Improve the wording only.
    {tailoring_section(user_request, covered_keywords=keep_keywords)}
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
# RECRUITER SNAPSHOT AGENT (a 10-15 second, half-page version of the resume)
#----------------------

def recruiter_snapshot_agent(user_request, final_resume_text):

    log_event("Recruiter Snapshot Agent Started")

    job_description = user_request.get("job_description") or ""
    target = (
        f"the job description below:\n{job_description}"
        if job_description
        else f"a {user_request['current_role'] or 'role matching their background'} role"
    )

    prompt = f"""
    Create a RECRUITER SNAPSHOT: a one-glance summary a recruiter can read in 10-15 seconds to
    decide whether this candidate fits {target}

    Source resume (the ONLY source of facts — never invent employers, titles, dates, metrics, or skills):
    {final_resume_text}

    Output plain text only (no Markdown: no **, no #, no backticks), in exactly this layout:
    Line 1: the candidate's full name
    Line 2: contact details separated by " | " (omit if none)
    ROLE FIT
    Two short sentences: who the candidate is (level, years, domain) and why they fit this role.
    KEY MATCHES
    - 3 to 4 bullets. Each pairs something the role needs with concrete evidence from the resume, ideally a number.
    CORE SKILLS
    2 to 3 lines, each "Category: skill, skill, skill" — only skills relevant to the role.
    RECENT EXPERIENCE
    The 2-3 most recent roles, one line each: "Title | Company | Dates". No bullets.
    EDUCATION
    One line per degree: "Degree | School | Year" (omit the section if none).

    Hard limit: 170 words in total. Every word must help the recruiter decide in seconds.
    """

    snapshot = call_llm(prompt)
    log_event("Recruiter snapshot generated")
    return {"snapshot": snapshot}

#----------------------
# ORCHESTRATOR (RAG step, parallel agents, progress callback)
#----------------------

PIPELINE_STEPS = [
    ("Profile Analyzer", "Reads your background and determines your experience level and domain."),
    ("ATS Match", "Scores your resume against the job (semantic RAG + keyword matching) and finds the gaps."),
    ("Resume Writer", "Rewrites your resume for the job's requirements and terminology, never inventing experience."),
    ("Human Optimizer", "Polishes the draft so it reads naturally, not like AI-generated text."),
    ("Completeness Check", "A guardrail that flags dropped jobs, rejects broken AI output, and keeps the higher-scoring version."),
    ("Reviewer", "Checks grammar, formatting, and consistency, with one-click fixes."),
    ("Recruiter Snapshot", "Condenses your resume into a half-page summary a recruiter can read in 15 seconds."),
    ("Cover Letter Writer", "Drafts a matching cover letter tailored to the same role."),
]


def orchestrator(user_request, request_id, progress_callback=None):
    log_event(f"{request_id}: Orchestrator started")
    start = time.time()

    def notify(message):
        # Only ever called from this (the caller's) thread — Streamlit UI updates are not thread-safe.
        log_event(f"{request_id}: {message}")
        if progress_callback:
            progress_callback(message)

    # RAG step — chunk + store resume, then retrieve JD-relevant chunks
    matched_chunks = []
    resume_text = user_request.get("resume_text")
    job_description = user_request.get("job_description")

    try:
        notify("Reading your resume...")
        if resume_text:
            store_resume_chunks(request_id, chunk_resume(resume_text))
            if job_description:
                notify("Matching your resume to the job description...")
                matched_chunks = retrieve_relevant_chunks(request_id, job_description)
    finally:
        # Resume chunks are only needed for retrieval — never keep them beyond this request.
        delete_resume_chunks(request_id)

    # The analyzer and cover letter only need the original resume, so they run in the background.
    # ATS -> writer -> optimizer must run in order: the writer targets the gaps the ATS agent finds.
    with ThreadPoolExecutor(max_workers=3) as pool:
        notify("Analyzing your profile and ATS gaps...")
        analyzer_future = pool.submit(analyzer_agent, user_request, request_id)
        cover_letter_future = pool.submit(cover_letter_agent, user_request, matched_chunks)
        ats_output = ats_agent(user_request, matched_chunks)

        notify("Writing your tailored resume...")
        resume_writer_output = resume_writer_agent(
            user_request, matched_chunks=matched_chunks, missing_keywords=ats_output["missing_keywords"],
            covered_keywords=ats_output["covered_keywords"],
        )
        draft_text = resume_writer_output["generated_resume"]

        notify("Polishing the final version...")
        # The optimizer must keep every job keyword the draft achieved, not just the original's.
        draft_keywords = keyword_coverage(draft_text, ats_output["job_keywords"])["covered"]
        human_optimizer_output = human_optimizer_agent(user_request, draft_text, keep_keywords=draft_keywords)
        polished_text = human_optimizer_output["human_friendly_resume"]

        notify("Checking content and picking the strongest version...")
        # Guardrails: the polished version must be a usable resume, keep every entry the draft kept,
        # and score at least as well against the job. Otherwise the draft is the better final resume.
        draft_completeness = check_completeness(resume_text, draft_text)
        polished_completeness = check_completeness(resume_text, polished_text)
        job_keywords = ats_output["job_keywords"]
        draft_scores = ats_breakdown(draft_text, job_description, user_request["skills"], job_keywords)
        polished_scores = ats_breakdown(polished_text, job_description, user_request["skills"], job_keywords)
        if not is_usable_resume(polished_text, resume_text):
            fallback_reason = "unusable output"
        elif polished_completeness["completeness_pct"] < draft_completeness["completeness_pct"]:
            fallback_reason = "dropped content"
        elif polished_scores["overall"] < draft_scores["overall"]:
            fallback_reason = "lower ATS score"
        else:
            fallback_reason = None

        if fallback_reason:
            log_event(f"{request_id}: using the Resume Writer draft ({fallback_reason})")
            human_optimizer_output = {"human_friendly_resume": draft_text, "fell_back_to_draft": True,
                                      "fallback_reason": fallback_reason}
            completeness_output, after = draft_completeness, draft_scores
        else:
            completeness_output, after = polished_completeness, polished_scores
        final_resume_text = human_optimizer_output["human_friendly_resume"]
        if completeness_output["possibly_missing"]:
            log_event(f"{request_id}: WARNING — {len(completeness_output['possibly_missing'])} entries possibly dropped")

        notify("Reviewing and building your recruiter snapshot...")
        reviewer_future = pool.submit(reviewer_agent, final_resume_text)
        snapshot_future = pool.submit(recruiter_snapshot_agent, user_request, final_resume_text)

        ats_output["before"] = {k: ats_output[k] for k in ("ats_score", "keyword_score", "semantic_score")}
        ats_output["after"] = {"ats_score": after["overall"], "keyword_score": after["keyword"], "semantic_score": after["semantic"]}
        ats_output["added_keywords"] = [k for k in after["covered"] if k not in ats_output["covered_keywords"]]
        ats_output["still_missing"] = after["missing"]
        ats_output["lost_keywords"] = [k for k in ats_output["covered_keywords"] if k not in after["covered"]]
        if ats_output["lost_keywords"]:
            log_event(f"{request_id}: WARNING — tailoring lost {len(ats_output['lost_keywords'])} job keywords")

        notify("Finishing up...")
        analyzer_output = analyzer_future.result()
        cover_letter_output = cover_letter_future.result()
        reviewer_output = reviewer_future.result()
        snapshot_output = snapshot_future.result()

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
            "recruiter_snapshot": snapshot_output,
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
    except ResumeGenerationError:
        raise HTTPException(status_code=502, detail="The AI could not produce a complete resume. Please try again.")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
