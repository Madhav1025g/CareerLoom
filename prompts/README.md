# Prompt versions

Each folder holds one version of the resume-tailoring prompts (`$name` placeholders are filled in by `main.py`).
The live site uses `PROMPT_VERSION` (env var `CAREERLOOM_PROMPT_VERSION`, default in `main.py`).

To try a change: copy the current version to a new folder, edit it, and compare them with the eval harness:

```bash
python -m evals compare --baseline v1 --candidate v2
```

Only switch the default once the new version wins without failing any checks.
