"""Structural checks: things that must hold for every tailored resume, whatever the exact wording."""
import main
from document_builder import parse_resume

def check(name: str, passed: bool, detail: str = "", hard: bool = True) -> dict:
    return {"name": name, "passed": bool(passed), "detail": detail, "hard": hard}


def _find_requirement(items: list[dict], term: str) -> dict | None:
    term_lower = term.lower()
    for item in items:
        if term_lower in item["text"].lower() or any(term_lower == k.lower() for k in item.get("keywords", [])):
            return item
    return None


def run_checks(case: dict, result: dict) -> list[dict]:
    request = case["request"]
    expect = case.get("expect", {})
    workflow = result["workflow"]
    original = request["resume_text"]
    final = workflow["human_optimizer"]["human_friendly_resume"] or ""
    requirement_match = workflow.get("requirement_match") or {}
    after_items = (requirement_match.get("after") or {}).get("items", [])
    checks = []

    # ---- always required
    checks.append(check("usable_output", main.is_usable_resume(final, original),
                        "" if main.is_usable_resume(final, original) else "Output is empty, too short, or a question"))

    completeness = main.check_completeness(original, final)
    checks.append(check("all_entries_kept", completeness["completeness_pct"] == 100,
                        "; ".join(completeness["possibly_missing"])))

    blocks = parse_resume(final)
    headings = sum(kind == "heading" for kind, _ in blocks)
    markdown = [line for line in final.splitlines() if line.lstrip().startswith("#") or "**" in line]
    format_ok = bool(blocks) and blocks[0][0] == "name" and headings >= 2 and not markdown
    checks.append(check("resume_format", format_ok,
                        f"{headings} section headings; {len(markdown)} Markdown lines" if not format_ok else ""))

    invented = main.invented_numbers(original, final, [request.get("experience_years", "")])
    checks.append(check("no_invented_numbers", not invented, f"New numbers: {', '.join(invented)}" if invented else ""))

    lost = workflow["ats_optimization"].get("lost_keywords", [])
    checks.append(check("job_keywords_kept", not lost, f"Lost: {', '.join(lost)}" if lost else ""))

    if request.get("job_description"):
        valid = True
        for key in ("before", "after"):
            evaluation = requirement_match.get(key) or {}
            score = evaluation.get("score")
            valid &= isinstance(score, int) and 0 <= score <= 100 and bool(evaluation.get("items"))
            valid &= all(i["status"] in main.STATUS_CREDIT for i in evaluation.get("items", []))
        checks.append(check("requirement_scores_valid", valid,
                            "" if valid else "Missing or out-of-range requirement scores/items"))

    # ---- case-specific expectations
    if "years_status" in expect:
        years_items = [i for i in after_items if i["category"] == "experience_years"]
        actual = years_items[0]["status"] if years_items else None
        checks.append(check("years_verdict", actual == expect["years_status"],
                            f"expected {expect['years_status']}, got {actual or 'no years requirement extracted'}"))

    for expected in expect.get("requirements", []):
        item = _find_requirement(after_items, expected["term"])
        actual = item["status"] if item else None
        checks.append(check(f"requirement:{expected['term']}", actual in expected["status"],
                            f"expected {'/'.join(expected['status'])}, got {actual or 'requirement not extracted'}"))

    for term in expect.get("must_not_contain", []):
        present = main.contains_term(final, term)
        checks.append(check(f"not_invented:{term}", not present,
                            f"'{term}' was added although the candidate never had it" if present else ""))

    score_range = expect.get("requirement_score_after")
    if score_range:
        score = (requirement_match.get("after") or {}).get("score")
        low, high = score_range.get("min", 0), score_range.get("max", 100)
        # Soft: a sanity range, not a pass/fail quality bar (LLM verdicts vary a little run to run).
        checks.append(check("requirement_score_in_range", score is not None and low <= score <= high,
                            f"expected {low}-{high}, got {score}", hard=False))
    return checks
