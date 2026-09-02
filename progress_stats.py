"""Pure-logic statistics over the problem-history store, backing the
sidebar Progress dashboard.

Deliberately streamlit-free (see AGENTS.md's hard rule on pure-logic
modules) so it stays plain-pytest-testable. Topic coverage is derived
from lesson_memory.infer_tags() -- the same lightweight keyword tagging
used for saved lessons -- rather than a new dependency or an AI call.

The input shape is the history dict exactly as problem_history.py builds
it (and persistence.load_problem_history rehydrates): keyed by problem
key, each value a snapshot with current_solution/current_hints/
attempt_errors/verification/language/problem_text. "Solved" counts
snapshots holding a generated solution; "hints only" counts snapshots
with hints but no solution (the two are mutually exclusive by the app's
display flow -- setting one clears the other).
"""

from lesson_memory import infer_tags


def summarize(history: dict) -> dict:
    """Aggregates one history dict into a small stats dict.

    Returns: total, solved, hints_only, fix_loop_problems (snapshots with
    at least one fix-loop attempt), fix_attempts (total attempts across
    those snapshots), verified_ok (snapshots whose verification both ran
    and passed), languages (count per language), topics (count per
    inferred lesson topic).
    """
    entries = list(history.values())
    languages = {}
    topics = {}
    fix_attempts = 0
    fix_loop_problems = 0
    solved = 0
    hints_only = 0
    verified_ok = 0
    for entry in entries:
        language = entry.get("language") or "Unknown"
        languages[language] = languages.get(language, 0) + 1
        for tag in infer_tags(entry.get("problem_text") or ""):
            topics[tag] = topics.get(tag, 0) + 1
        if entry.get("current_solution"):
            solved += 1
        elif entry.get("current_hints"):
            hints_only += 1
        errors = entry.get("attempt_errors") or []
        if errors:
            fix_loop_problems += 1
            fix_attempts += len(errors)
        verification = entry.get("verification") or {}
        if verification.get("verified") and verification.get("passed"):
            verified_ok += 1
    return {
        "total": len(entries),
        "solved": solved,
        "hints_only": hints_only,
        "fix_loop_problems": fix_loop_problems,
        "fix_attempts": fix_attempts,
        "verified_ok": verified_ok,
        "languages": languages,
        "topics": topics,
    }
