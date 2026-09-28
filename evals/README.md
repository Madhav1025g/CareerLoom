# Eval harness

Measures the quality of CareerLoom's resume tailoring on a golden set of **fictional** resumes and job
descriptions (`cases/`), so prompt changes are judged by data instead of by eye.

Each case runs through the real pipeline (requirement extraction, writer, optimizer, requirement check) and is
graded two ways:

| Grader | What it checks | Gate rule |
|---|---|---|
| **Structural checks** (`checks.py`) | usable output · every job kept · resume format · no invented numbers · job keywords kept · valid requirement scores · case expectations (years verdict, specific requirements, skills that must not be invented) | Any hard check failing fails the gate |
| **LLM judge** (`judge.py`) | 1–5 rubric: truthfulness, job relevance, completeness, readability, ATS format, scored by a different model family (`qwen/qwen3.8-27b` on Groq, override with `EVAL_JUDGE_MODEL`) | Fails if the mean drops > 0.3 below the baseline (truthfulness has its own 0.3 bar) |

Mean requirement match and ATS match after tailoring must also stay within 5 points of the baseline.

## Commands

```bash
python -m evals run                         # run all cases with the live prompt version
python -m evals run --cases years_short     # run a single case
python -m evals run --save-baseline         # store the result as evals/baseline.json
python -m evals run --refresh-requirements  # re-extract each case's requirements (after changing extraction)
python -m evals compare --baseline v1 --candidate v2
python -m evals gate                        # run + compare with the baseline; exit code 1 if quality dropped
```

Exit codes: `0` pass · `1` quality dropped · `2` could not run (missing key, rate limit).

## Setup

Needs `GROQ_API_KEY` in the project's `.env` file locally, and as a GitHub Actions repository secret for CI.
A full run makes about 30 API calls (plus one judge call per case), so the CI gate only runs when `main.py`,
`prompts/`, or `evals/` change, or when started manually from the Actions tab.

## Frozen requirements

Each golden job's extracted requirements are stored in `requirements.json`, so every run grades against identical
lists and the gate measures prompt changes, not extraction noise. After changing the requirement-extraction
prompt, refresh them and the baseline: `python -m evals run --refresh-requirements --save-baseline`.

## Changing prompts

1. Copy `prompts/v1` to a new folder (e.g. `prompts/v3`) and edit it.
2. `python -m evals compare --baseline v1 --candidate v3`
3. If it passes and scores better, make it the live version (`PROMPT_VERSION` in `main.py`) and refresh the
   baseline with `python -m evals run --save-baseline`.

## Adding a case

Add a JSON file to `cases/` with `id`, `title`, `why`, `request` (the pipeline input), and `expect`
(`years_status`, `requirements: [{term, status}]`, `must_not_contain`, `requirement_score_after: {min, max}`).
Always use fictional people.
