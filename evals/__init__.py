"""
CareerLoom evaluation harness.

Runs the resume-tailoring pipeline on a golden set of fictional resumes and job descriptions (evals/cases/),
then grades each result two ways:

- checks.py — structural checks that must always hold (no invented numbers, no dropped jobs, correct
  years-of-experience verdicts, ...). Any failure fails the quality gate.
- judge.py  — an LLM-as-judge rubric from a different model family, compared against a saved baseline.

Usage: python -m evals --help
"""
import os

# Evals must be reproducible locally and in CI: always score without Qdrant/embeddings (the semantic part of the
# ATS score is skipped identically everywhere). load_dotenv() in main.py never overrides a variable already set.
os.environ["QDRANT_URL"] = ""
