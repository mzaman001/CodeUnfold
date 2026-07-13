import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from problem_history import history_key, build_snapshot, has_content, cap_history, recent_entries


# ---------- history_key ----------

def test_history_key_deterministic():
    assert history_key("Two Sum problem", "Python") == history_key("Two Sum problem", "Python")


def test_history_key_differs_by_language():
    assert history_key("Two Sum", "Python") != history_key("Two Sum", "JavaScript")


def test_history_key_differs_by_problem_text():
    assert history_key("Two Sum", "Python") != history_key("Valid Parentheses", "Python")


def test_history_key_normalizes_surrounding_whitespace():
    assert history_key("Two Sum", "Python") == history_key("  Two Sum  ", "Python")


def test_history_key_handles_none_language():
    # Must not raise even with unexpected None input.
    assert history_key("problem", None) == history_key("problem", None)


# ---------- build_snapshot ----------

def test_build_snapshot_captures_all_fields():
    snap = build_snapshot(
        problem_text="Two Sum", language="Python",
        current_solution="<solution/>", current_hints=None,
        raw_code="def f(): pass", verification={"verified": True, "passed": True},
        attempt_errors=["err1"], title="Two Sum",
    )
    assert snap["problem_text"] == "Two Sum"
    assert snap["language"] == "Python"
    assert snap["current_solution"] == "<solution/>"
    assert snap["current_hints"] is None
    assert snap["raw_code"] == "def f(): pass"
    assert snap["verification"] == {"verified": True, "passed": True}
    assert snap["attempt_errors"] == ["err1"]
    assert snap["title"] == "Two Sum"
    assert "timestamp" in snap


def test_build_snapshot_copies_attempt_errors_not_aliases():
    """The snapshot must not share a list reference with the live
    session state -- otherwise clearing/mutating the live list later
    would silently corrupt the "frozen" history entry too."""
    errors = ["err1"]
    snap = build_snapshot(
        problem_text="p", language="Python", current_solution="s", current_hints=None,
        raw_code="", verification=None, attempt_errors=errors, title="t",
    )
    errors.append("err2")
    assert snap["attempt_errors"] == ["err1"]  # unaffected by the later mutation


def test_build_snapshot_handles_empty_attempt_errors():
    snap = build_snapshot(
        problem_text="p", language="Python", current_solution="s", current_hints=None,
        raw_code="", verification=None, attempt_errors=[], title="t",
    )
    assert snap["attempt_errors"] == []

    snap2 = build_snapshot(
        problem_text="p", language="Python", current_solution="s", current_hints=None,
        raw_code="", verification=None, attempt_errors=None, title="t",
    )
    assert snap2["attempt_errors"] == []


# ---------- has_content ----------

def test_has_content_true_with_solution():
    assert has_content("some solution", None) is True


def test_has_content_true_with_hints():
    assert has_content(None, "some hints") is True


def test_has_content_false_when_both_empty():
    assert has_content(None, None) is False
    assert has_content("", "") is False


# ---------- cap_history ----------

def test_cap_history_noop_under_limit():
    history = {f"k{i}": {"timestamp": i} for i in range(5)}
    result = cap_history(history, max_entries=10)
    assert len(result) == 5


def test_cap_history_evicts_oldest_first():
    history = {f"k{i}": {"timestamp": i} for i in range(10)}
    result = cap_history(history, max_entries=5)
    assert len(result) == 5
    # The 5 with the highest timestamps (5..9) should remain.
    assert set(result.keys()) == {"k5", "k6", "k7", "k8", "k9"}


def test_cap_history_exact_boundary_not_evicted():
    history = {f"k{i}": {"timestamp": i} for i in range(5)}
    result = cap_history(history, max_entries=5)
    assert len(result) == 5


# ---------- recent_entries ----------

def test_recent_entries_returns_newest_first():
    history = {
        "old": {"timestamp": 1, "title": "Old"},
        "new": {"timestamp": 3, "title": "New"},
        "mid": {"timestamp": 2, "title": "Mid"},
    }
    result = recent_entries(history, limit=5)
    assert [key for key, _ in result] == ["new", "mid", "old"]


def test_recent_entries_respects_limit():
    history = {f"k{i}": {"timestamp": i} for i in range(10)}
    result = recent_entries(history, limit=3)
    assert len(result) == 3


def test_recent_entries_empty_history_returns_empty_list():
    assert recent_entries({}, limit=5) == []
