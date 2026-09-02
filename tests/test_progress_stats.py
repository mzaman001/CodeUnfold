import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from progress_stats import summarize


def _entry(**overrides):
    """Builds a history snapshot in the shape problem_history.build_snapshot()
    produces, so the stats tests exercise the real record structure."""
    entry = {
        "problem_text": "Example: Input: nums = [2,7,11,15], target = 9 -> Output: [0,1]",
        "language": "Python",
        "current_solution": "<title>Two Sum</title>",
        "current_hints": None,
        "raw_code": "",
        "verification": {"verified": True, "passed": True, "results": [], "reason": ""},
        "attempt_errors": [],
        "title": "Two Sum",
        "timestamp": 1.0,
    }
    entry.update(overrides)
    return entry


def test_summarize_empty_history():
    stats = summarize({})
    assert stats["total"] == 0
    assert stats["solved"] == 0
    assert stats["hints_only"] == 0
    assert stats["fix_loop_problems"] == 0
    assert stats["fix_attempts"] == 0
    assert stats["verified_ok"] == 0
    assert stats["languages"] == {}
    assert stats["topics"] == {}


def test_summarize_counts_solved_and_hints_only():
    stats = summarize({
        "a": _entry(),
        "b": _entry(current_solution=None, current_hints="<intuition>x</intuition>"),
    })
    assert stats["total"] == 2
    assert stats["solved"] == 1
    assert stats["hints_only"] == 1


def test_summarize_counts_fix_loops_and_attempts():
    stats = summarize({
        "a": _entry(attempt_errors=["Error 1", "Error 2"]),
        "b": _entry(attempt_errors=[]),
        "c": _entry(current_solution=None, current_hints="<intuition>x</intuition>", attempt_errors=["Error 3"]),
    })
    assert stats["fix_loop_problems"] == 2
    assert stats["fix_attempts"] == 3


def test_summarize_language_breakdown():
    stats = summarize({
        "a": _entry(language="Python"),
        "b": _entry(language="Python"),
        "c": _entry(language="JavaScript"),
    })
    assert stats["languages"] == {"Python": 2, "JavaScript": 1}


def test_summarize_topic_coverage_uses_infer_tags():
    stats = summarize({
        "a": _entry(),  # contains "nums" -> Array
        "b": _entry(problem_text="Given a linked list, reverse it"),
    })
    assert stats["topics"].get("Array") == 1
    assert stats["topics"].get("Linked List") == 1


def test_summarize_counts_verified_solutions():
    stats = summarize({
        "a": _entry(),
        "b": _entry(verification={"verified": True, "passed": False, "results": [], "reason": ""}),
        "c": _entry(verification=None),
    })
    assert stats["verified_ok"] == 1
