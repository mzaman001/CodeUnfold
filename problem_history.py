"""Pure-logic helpers for problem history: letting a user switch back to
a previously-worked-on problem (with its solution/hints/code intact)
instead of losing it the moment they paste a new problem, click hints
again, or click Fix on the same problem.

This is deliberately a *history*, not a full undo stack: one entry per
distinct (problem_text, language) pair, continuously updated in place as
the user works on it (e.g. successive fix-loop attempts overwrite the
same entry with the latest version) rather than one entry per action.
Switching to a different problem preserves the old entry; coming back to
a problem you've already worked on restores its most recent state.

No Streamlit imports here by design (see AGENTS.md's hard rule on
pure-logic modules) -- the Streamlit-aware orchestration (deciding when
to snapshot, writing into st.session_state, rendering the restore
buttons) lives in main.py.
"""
import hashlib
import time

MAX_HISTORY_ENTRIES = 15


def history_key(problem_text: str, language: str) -> str:
    """Stable key for a (problem_text, language) pair.

    Whitespace differences at the edges are normalized away (a
    resubmitted problem with trailing whitespace shouldn't be treated as
    a different problem), but the text is otherwise taken as-is --
    intentionally simple rather than fuzzy-matching near-duplicate
    problem text, which would risk conflating two actually-different
    problems.
    """
    normalized = (problem_text or "").strip() + "||" + (language or "")
    return hashlib.sha256(normalized.encode()).hexdigest()[:16]


def build_snapshot(
    problem_text: str, language: str, current_solution, current_hints,
    raw_code: str, verification, attempt_errors: list, title: str,
) -> dict:
    """Builds one history entry capturing everything needed to fully
    restore a problem's state without re-calling the AI."""
    return {
        "problem_text": problem_text,
        "language": language,
        "current_solution": current_solution,
        "current_hints": current_hints,
        "raw_code": raw_code,
        "verification": verification,
        "attempt_errors": list(attempt_errors) if attempt_errors else [],
        "title": title,
        "timestamp": time.time(),
    }


def has_content(current_solution, current_hints) -> bool:
    """Whether there's anything worth snapshotting at all -- an empty
    problem with no generated solution/hints isn't history yet."""
    return bool(current_solution or current_hints)


def cap_history(history: dict, max_entries: int = MAX_HISTORY_ENTRIES) -> dict:
    """FIFO-evicts the oldest entries (by timestamp) beyond max_entries.

    Mutates and returns the same dict for convenience at call sites.
    """
    if len(history) <= max_entries:
        return history
    oldest_first = sorted(history.keys(), key=lambda k: history[k].get("timestamp", 0))
    for key in oldest_first[: len(history) - max_entries]:
        del history[key]
    return history


def recent_entries(history: dict, limit: int = 5) -> list:
    """Returns up to `limit` most recent (key, entry) pairs, newest first."""
    ordered = sorted(history.items(), key=lambda item: item[1].get("timestamp", 0), reverse=True)
    return ordered[:limit]
