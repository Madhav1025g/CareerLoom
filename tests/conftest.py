"""
Shared test setup: no real API keys, no network. The LLM and embedding model are replaced
with deterministic fakes so the whole pipeline runs offline in about a second.
"""
import hashlib
import json
import os
import re
import sys
from pathlib import Path

import numpy as np
import pytest

# Must be set before main.py is imported — load_dotenv() never overrides existing variables.
for var in ("QDRANT_URL", "QDRANT_API_KEY", "GROQ_API_KEY", "OPENAI_API_KEY"):
    os.environ[var] = ""
os.environ["API_KEY_HERE"] = "test-key-123"

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import main  # noqa: E402

SOURCE_RESUME = """Jordan Lee
jordan.lee@email.com | (555) 123-4567 | Boston, MA

PROFESSIONAL SUMMARY
Backend Software Engineer with 5 years of experience building REST APIs and cloud-native services.

EXPERIENCE
Software Engineer | TechCorp Inc. | Remote | Jan 2021 - Present
- Built and maintained REST APIs serving 1M+ daily requests using Python and FastAPI
- Deployed microservices on AWS Lambda and ECS, reducing infrastructure costs by 20%
Junior Developer | StartupX | Austin, TX | 2019 - 2020
- Developed internal dashboards in React

TECHNICAL SKILLS
Languages: Python, JavaScript, SQL
Cloud & DevOps: AWS, Docker, GitHub Actions

EDUCATION
B.S. Computer Science | University of Massachusetts | 2019
"""

TAILORED_RESUME = SOURCE_RESUME.replace(
    "Backend Software Engineer with 5 years",
    "Backend Software Engineer specializing in Python, FastAPI, AWS, and Docker, with 5 years",
)

SNAPSHOT = """Jordan Lee
jordan.lee@email.com | Boston, MA
ROLE FIT
Backend engineer with 5 years building Python APIs on AWS; a strong match for this role.
KEY MATCHES
- REST APIs at scale: 1M+ daily requests with FastAPI
CORE SKILLS
Languages: Python, SQL
RECENT EXPERIENCE
Software Engineer | TechCorp Inc. | Jan 2021 - Present
"""

REQUEST = {
    "full_name": "Jordan Lee",
    "current_role": "Software Engineer",
    "skills": ["Python", "FastAPI", "AWS", "Docker"],
    "experience_years": 5,
    "resume_text": SOURCE_RESUME,
    "resume_file": None,
    "job_description": "Backend engineer with Python, FastAPI, AWS, Docker, and Kubernetes experience.",
}


# Fake requirement extraction: keywords dedupe to Python, FastAPI, AWS, Docker, Kubernetes.
REQUIREMENTS = [
    {"text": "3+ years of backend experience", "category": "experience_years", "importance": "required",
     "min_years": 3, "max_years": None, "keywords": []},
    {"text": "Python", "category": "skill", "importance": "required", "keywords": ["Python"]},
    {"text": "FastAPI web services", "category": "skill", "importance": "required", "keywords": ["FastAPI", "Python"]},
    {"text": "AWS cloud experience", "category": "skill", "importance": "required", "keywords": ["AWS"]},
    {"text": "Containers with Docker", "category": "skill", "importance": "required", "keywords": ["Docker"]},
    {"text": "Kubernetes", "category": "skill", "importance": "preferred", "keywords": ["Kubernetes"]},
    {"text": "Strong backend fundamentals", "category": "knowledge", "importance": "required", "keywords": []},
    {"text": "Collaborative team player", "category": "soft_skill", "importance": "required", "keywords": []},
]

# Fake judge verdicts, keyed by the ids extraction assigns (r1 = years, judged in code).
JUDGEMENTS = json.dumps({"results": [
    {"id": "r2", "status": "met", "evidence": "Languages: Python, JavaScript, SQL", "reason": "Listed and used."},
    {"id": "r3", "status": "met", "evidence": "REST APIs serving 1M+ daily requests using Python and FastAPI", "reason": "Built APIs."},
    {"id": "r4", "status": "met", "evidence": "Deployed microservices on AWS Lambda and ECS", "reason": "Deployed on AWS."},
    {"id": "r5", "status": "met", "evidence": "Cloud & DevOps: AWS, Docker, GitHub Actions", "reason": "Listed."},
    {"id": "r6", "status": "not_met", "evidence": "", "reason": "No Kubernetes experience shown."},
    {"id": "r7", "status": "met", "evidence": "Built and maintained REST APIs serving 1M+ daily requests", "reason": "Shows fundamentals."},
    {"id": "r8", "status": "partial", "evidence": "a quote that is not in the resume", "reason": "Implied."},
]})


def requirements_json(requirements):
    return "Here you go: " + json.dumps({"requirements": requirements})


def fake_llm(prompt: str, **kwargs) -> str:
    """Route each agent's prompt to a canned response."""
    if "candidate_level" in prompt:
        return '```json\n{"candidate_level": "Mid-Level", "primary_domain": "Backend", "years_experience": 5}\n```'
    if '"requirements": [' in prompt:
        return requirements_json(REQUIREMENTS)
    if '"results": [' in prompt:
        return JUDGEMENTS
    if "JSON array" in prompt:
        return ('[{"issue": "Grammar", "current_text": "Developed internal dashboards in React", '
                '"suggested_fix": "Developed internal analytics dashboards in React"},'
                ' {"issue": "No-op", "current_text": "same", "suggested_fix": "same"}]')
    if "RECRUITER SNAPSHOT" in prompt:
        return SNAPSHOT
    if "cover letter" in prompt:
        return "Dear Hiring Manager,\n\nI am excited to apply.\n\nSincerely,\nJordan Lee"
    return TAILORED_RESUME


class FakeEmbedder:
    """Deterministic bag-of-words hashing embedder: texts sharing words get similar vectors."""

    dim = 64

    def _one(self, text):
        vec = np.zeros(self.dim)
        for word in re.findall(r"[a-z0-9]+", text.lower()):
            vec[int(hashlib.md5(word.encode()).hexdigest(), 16) % self.dim] += 1.0
        return vec if vec.any() else np.ones(self.dim)

    def encode(self, texts):
        if isinstance(texts, str):
            return self._one(texts)
        return np.array([self._one(t) for t in texts])


@pytest.fixture
def pipeline(monkeypatch):
    """main module wired with the fake LLM and fake embedder."""
    monkeypatch.setattr(main, "call_llm", fake_llm)
    monkeypatch.setattr(main, "embedding_model", FakeEmbedder())
    return main


@pytest.fixture(autouse=True)
def fresh_keyword_cache():
    """Each test starts with an empty job-keyword cache so fakes aren't shadowed by earlier tests."""
    main._JOB_REQUIREMENTS_CACHE.clear()
    yield
    main._JOB_REQUIREMENTS_CACHE.clear()
