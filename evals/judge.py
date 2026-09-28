"""LLM-as-judge: a different model family grades each tailored resume against a fixed rubric."""
import os

import main

# A different (and larger) model than the one that writes the resumes, so it isn't grading its own style.
# Free on Groq with its own rate limits. Override with EVAL_JUDGE_MODEL if Groq retires it.
JUDGE_MODEL = os.getenv("EVAL_JUDGE_MODEL", "llama-3.3-70b-versatile")

RUBRIC = {
    "truthfulness": "Every claim is supported by the original resume. 5 = nothing invented; 1 = invented "
                    "employers, skills, titles, or numbers.",
    "job_relevance": "The resume foregrounds the experience this job asks for, using the job's terminology where "
                     "the candidate genuinely matches. 5 = clearly targeted; 1 = generic.",
    "completeness": "All jobs, projects, education, and key achievements from the original are kept. 5 = nothing "
                    "important lost; 1 = major content dropped.",
    "readability": "Clear, concise, natural, professional wording a recruiter can scan quickly. 5 = excellent; "
                   "1 = awkward, repetitive, or robotic.",
    "ats_format": "Clean plain-text structure: name, contact line, ALL-CAPS section headings, one header line per "
                  "job, bullet points, no tables or Markdown. 5 = perfect; 1 = unusable.",
}


def judge_resume(original: str, job_description: str | None, tailored: str) -> dict:
    """Score a tailored resume 1-5 on each rubric dimension. Returns scores, their mean, and flagged claims."""
    rubric = "\n".join(f'- "{name}": {description}' for name, description in RUBRIC.items())
    prompt = f"""
    You are a strict, experienced recruiter auditing an AI-tailored resume. Compare it with the ORIGINAL resume
    and the JOB DESCRIPTION, then score each dimension from 1 to 5 (integers) using this rubric:
    {rubric}

    Also list any claims in the tailored resume that the original does not support ("unsupported_claims"), quoting
    them briefly. Be critical: a 5 means you would not change anything.

    ORIGINAL RESUME:
    {original}

    JOB DESCRIPTION:
    {(job_description or "(none provided)")[:main.JD_PROMPT_CHARS]}

    TAILORED RESUME:
    {tailored}

    Return ONLY JSON (no prose, no markdown fences):
    {{"scores": {{{", ".join(f'"{name}": 0' for name in RUBRIC)}}}, "unsupported_claims": [], "notes": "one sentence"}}
    """
    for _ in range(2):
        parsed = main.parse_json_object(main.call_llm(prompt, temperature=0, model=JUDGE_MODEL))
        raw = parsed.get("scores") if isinstance(parsed.get("scores"), dict) else {}
        scores = {}
        for name in RUBRIC:
            try:
                value = int(raw.get(name))
            except (TypeError, ValueError):
                break
            if 1 <= value <= 5:
                scores[name] = value
        if len(scores) == len(RUBRIC):
            claims = parsed.get("unsupported_claims") if isinstance(parsed.get("unsupported_claims"), list) else []
            return {"scores": scores, "overall": round(sum(scores.values()) / len(scores), 2),
                    "unsupported_claims": [str(c) for c in claims][:10], "notes": str(parsed.get("notes", ""))}
    return {"scores": None, "overall": None, "unsupported_claims": [], "notes": "Judge output could not be parsed"}
