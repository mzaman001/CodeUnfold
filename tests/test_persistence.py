import sys
import os
import sqlite3
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from persistence import (
    init_db, save_lesson_to_db, load_lessons_from_db,
    delete_client_lessons, delete_last_lesson, new_client_id, get_db_path, DB_ENV_VAR,
    save_problem_history, load_problem_history, delete_client_history,
    save_socratic_conversation, load_socratic_conversations, delete_client_socratic,
)


def test_new_client_id_is_unique_and_short():
    a, b = new_client_id(), new_client_id()
    assert a != b
    assert len(a) == 16


def test_init_db_creates_table(tmp_path):
    db_path = str(tmp_path / "test.db")
    assert init_db(db_path) is True
    assert os.path.exists(db_path)


def test_init_db_creates_problem_history_and_socratic_tables(tmp_path):
    db_path = str(tmp_path / "test.db")
    assert init_db(db_path) is True
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    names = {row[0] for row in rows}
    assert "lessons" in names
    assert "problem_history" in names
    assert "socratic_conversations" in names


def test_init_db_is_idempotent_across_new_tables(tmp_path):
    """Re-running init_db on an existing database (the normal app boot
    path, which happens once per session) must not error out or duplicate
    anything -- the CREATE TABLE IF NOT EXISTS guards make it a no-op."""
    db_path = str(tmp_path / "test.db")
    assert init_db(db_path) is True
    assert init_db(db_path) is True


def test_init_db_fails_gracefully_on_bad_path():
    # A path inside a nonexistent directory should fail to open, not raise.
    assert init_db("/nonexistent_dir_xyz/test.db") is False


def test_save_and_load_lesson_roundtrip(tmp_path):
    db_path = str(tmp_path / "test.db")
    init_db(db_path)
    client_id = new_client_id()
    lesson = {"title": "Two Sum", "takeaway": "use a hash map", "tags": ["Hash Map", "Array"], "language": "Python"}

    assert save_lesson_to_db(db_path, client_id, lesson) is True
    loaded = load_lessons_from_db(db_path, client_id)

    assert len(loaded) == 1
    assert loaded[0]["title"] == "Two Sum"
    assert loaded[0]["takeaway"] == "use a hash map"
    assert loaded[0]["tags"] == ["Hash Map", "Array"]
    assert loaded[0]["language"] == "Python"


def test_load_lessons_isolated_by_client_id(tmp_path):
    db_path = str(tmp_path / "test.db")
    init_db(db_path)
    client_a, client_b = new_client_id(), new_client_id()

    save_lesson_to_db(db_path, client_a, {"title": "A", "takeaway": "ta", "tags": [], "language": "Python"})
    save_lesson_to_db(db_path, client_b, {"title": "B", "takeaway": "tb", "tags": [], "language": "Python"})

    assert [lesson["title"] for lesson in load_lessons_from_db(db_path, client_a)] == ["A"]
    assert [lesson["title"] for lesson in load_lessons_from_db(db_path, client_b)] == ["B"]


def test_load_lessons_preserves_order(tmp_path):
    db_path = str(tmp_path / "test.db")
    init_db(db_path)
    client_id = new_client_id()
    for i in range(3):
        save_lesson_to_db(db_path, client_id, {"title": f"L{i}", "takeaway": "t", "tags": [], "language": "Python"})

    loaded = load_lessons_from_db(db_path, client_id)
    assert [lesson["title"] for lesson in loaded] == ["L0", "L1", "L2"]


def test_load_lessons_respects_limit(tmp_path):
    db_path = str(tmp_path / "test.db")
    init_db(db_path)
    client_id = new_client_id()
    for i in range(10):
        save_lesson_to_db(db_path, client_id, {"title": f"L{i}", "takeaway": "t", "tags": [], "language": "Python"})

    assert len(load_lessons_from_db(db_path, client_id, limit=3)) == 3


def test_load_lessons_for_unknown_client_returns_empty_list(tmp_path):
    db_path = str(tmp_path / "test.db")
    init_db(db_path)
    assert load_lessons_from_db(db_path, "never-seen-client") == []


def test_load_lessons_from_missing_db_returns_empty_list_not_raises(tmp_path):
    db_path = str(tmp_path / "does_not_exist.db")
    # No init_db call -- file doesn't exist. sqlite3.connect will still
    # create an empty file but the table won't exist; the SELECT should
    # fail internally and be caught, returning [] rather than raising.
    assert load_lessons_from_db(db_path, "someone") == []


def test_delete_client_lessons_removes_only_that_client(tmp_path):
    db_path = str(tmp_path / "test.db")
    init_db(db_path)
    client_a, client_b = new_client_id(), new_client_id()
    save_lesson_to_db(db_path, client_a, {"title": "A", "takeaway": "ta", "tags": [], "language": "Python"})
    save_lesson_to_db(db_path, client_b, {"title": "B", "takeaway": "tb", "tags": [], "language": "Python"})

    assert delete_client_lessons(db_path, client_a) is True
    assert load_lessons_from_db(db_path, client_a) == []
    assert len(load_lessons_from_db(db_path, client_b)) == 1


def test_delete_last_lesson_removes_only_the_most_recent(tmp_path):
    db_path = str(tmp_path / "test.db")
    init_db(db_path)
    client_id = new_client_id()
    for i in range(3):
        save_lesson_to_db(db_path, client_id, {"title": f"L{i}", "takeaway": "t", "tags": [], "language": "Python"})

    assert delete_last_lesson(db_path, client_id) is True
    remaining = load_lessons_from_db(db_path, client_id)
    assert [lesson["title"] for lesson in remaining] == ["L0", "L1"]


def test_delete_last_lesson_does_not_affect_other_clients(tmp_path):
    db_path = str(tmp_path / "test.db")
    init_db(db_path)
    client_a, client_b = new_client_id(), new_client_id()
    save_lesson_to_db(db_path, client_a, {"title": "A", "takeaway": "ta", "tags": [], "language": "Python"})
    save_lesson_to_db(db_path, client_b, {"title": "B", "takeaway": "tb", "tags": [], "language": "Python"})

    delete_last_lesson(db_path, client_a)
    assert load_lessons_from_db(db_path, client_a) == []
    assert len(load_lessons_from_db(db_path, client_b)) == 1


def test_delete_last_lesson_on_empty_client_does_not_raise(tmp_path):
    db_path = str(tmp_path / "test.db")
    init_db(db_path)
    assert delete_last_lesson(db_path, "never-seen-client") is True


def _snapshot(**overrides):
    """Builds a snapshot in the exact shape problem_history.build_snapshot()
    produces, so the roundtrip tests exercise the real record structure."""
    snap = {
        "problem_text": "Example: Input: nums = [2,7,11,15], target = 9 -> Output: [0,1]",
        "language": "Python",
        "current_solution": "<title>Two Sum</title><takeaway>use a hash map</takeaway>",
        "current_hints": None,
        "raw_code": "class Solution:\n    def twoSum(self, nums, target):\n        return []\n",
        "verification": {"verified": True, "passed": True, "results": [], "reason": ""},
        "attempt_errors": ["IndexError: list index out of range"],
        "title": "Two Sum",
        "timestamp": 1234.5,
    }
    snap.update(overrides)
    return snap


def test_save_and_load_problem_history_roundtrip(tmp_path):
    db_path = str(tmp_path / "test.db")
    init_db(db_path)
    client_id = new_client_id()
    snapshot = _snapshot()

    assert save_problem_history(db_path, client_id, "key1", snapshot) is True
    loaded = load_problem_history(db_path, client_id)

    assert set(loaded.keys()) == {"key1"}
    assert loaded["key1"] == snapshot


def test_save_problem_history_preserves_none_verification(tmp_path):
    db_path = str(tmp_path / "test.db")
    init_db(db_path)
    client_id = new_client_id()

    save_problem_history(db_path, client_id, "key1", _snapshot(verification=None))
    loaded = load_problem_history(db_path, client_id)

    assert loaded["key1"]["verification"] is None


def test_save_problem_history_upserts_same_key(tmp_path):
    db_path = str(tmp_path / "test.db")
    init_db(db_path)
    client_id = new_client_id()

    save_problem_history(db_path, client_id, "key1", _snapshot(title="First version"))
    save_problem_history(db_path, client_id, "key1", _snapshot(title="Second version"))
    loaded = load_problem_history(db_path, client_id)

    # One row per problem, holding the latest state -- mirrors the
    # in-memory history dict's overwrite-in-place behavior.
    assert len(loaded) == 1
    assert loaded["key1"]["title"] == "Second version"


def test_load_problem_history_isolated_by_client_id(tmp_path):
    db_path = str(tmp_path / "test.db")
    init_db(db_path)
    client_a, client_b = new_client_id(), new_client_id()

    save_problem_history(db_path, client_a, "keyA", _snapshot(title="A"))
    save_problem_history(db_path, client_b, "keyB", _snapshot(title="B"))

    assert list(load_problem_history(db_path, client_a).keys()) == ["keyA"]
    assert list(load_problem_history(db_path, client_b).keys()) == ["keyB"]


def test_load_problem_history_missing_db_returns_empty(tmp_path):
    db_path = str(tmp_path / "does_not_exist.db")
    assert load_problem_history(db_path, "someone") == {}


def test_load_problem_history_skips_corrupt_json_row(tmp_path):
    """A row with corrupt JSON (e.g. a partially-written write) must be
    skipped, not crash the whole load -- the good rows still come back."""
    db_path = str(tmp_path / "test.db")
    init_db(db_path)
    client_id = new_client_id()

    save_problem_history(db_path, client_id, "good", _snapshot(title="Good"))
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO problem_history (client_id, problem_key, problem_text, language, "
            "title, current_solution, current_hints, raw_code, verification, attempt_errors, timestamp) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (client_id, "corrupt", "text", "Python", "Corrupt", None, None, "",
             "{not json", "[]", 9999.0),
        )
        conn.commit()

    loaded = load_problem_history(db_path, client_id)
    assert list(loaded.keys()) == ["good"]


def test_save_problem_history_missing_required_key_fails_gracefully(tmp_path):
    db_path = str(tmp_path / "test.db")
    init_db(db_path)
    # Missing "problem_text" -- should return False, not raise.
    assert save_problem_history(db_path, new_client_id(), "key1", {"title": "no text"}) is False


def test_delete_client_history_clears_only_that_client(tmp_path):
    db_path = str(tmp_path / "test.db")
    init_db(db_path)
    client_a, client_b = new_client_id(), new_client_id()

    save_problem_history(db_path, client_a, "keyA", _snapshot(title="A"))
    save_problem_history(db_path, client_b, "keyB", _snapshot(title="B"))

    assert delete_client_history(db_path, client_a) is True
    assert load_problem_history(db_path, client_a) == {}
    assert list(load_problem_history(db_path, client_b).keys()) == ["keyB"]


def _conversation(**overrides):
    conv = {
        "conversation": [
            {"question": "What would you do by hand?", "answer": "check every pair"},
        ],
        "pending_question": "How would you avoid checking pairs twice?",
        "problem_text": "Example: Input: nums = [2,7,11,15], target = 9 -> Output: [0,1]",
        "language": "Python",
    }
    conv.update(overrides)
    return conv


def test_save_and_load_socratic_conversation_roundtrip(tmp_path):
    db_path = str(tmp_path / "test.db")
    init_db(db_path)
    client_id = new_client_id()

    data = _conversation()
    assert save_socratic_conversation(
        db_path, client_id, "key1",
        data["problem_text"], data["language"], data["conversation"], data["pending_question"],
    ) is True

    loaded = load_socratic_conversations(db_path, client_id)
    assert set(loaded.keys()) == {"key1"}
    assert loaded["key1"]["conversation"] == data["conversation"]
    assert loaded["key1"]["pending_question"] == data["pending_question"]
    assert loaded["key1"]["problem_text"] == data["problem_text"]


def test_save_socratic_conversation_upserts_same_key(tmp_path):
    db_path = str(tmp_path / "test.db")
    init_db(db_path)
    client_id = new_client_id()

    first = _conversation(pending_question="Round 1 question")
    second = _conversation(pending_question="Round 2 question")
    save_socratic_conversation(
        db_path, client_id, "key1", first["problem_text"], first["language"],
        first["conversation"], first["pending_question"],
    )
    save_socratic_conversation(
        db_path, client_id, "key1", second["problem_text"], second["language"],
        second["conversation"], second["pending_question"],
    )

    loaded = load_socratic_conversations(db_path, client_id)
    assert len(loaded) == 1
    assert loaded["key1"]["pending_question"] == "Round 2 question"


def test_load_socratic_conversations_isolated_by_client_id(tmp_path):
    db_path = str(tmp_path / "test.db")
    init_db(db_path)
    client_a, client_b = new_client_id(), new_client_id()

    a = _conversation()
    b = _conversation(problem_text="Different problem")
    save_socratic_conversation(
        db_path, client_a, "keyA", a["problem_text"], a["language"], a["conversation"], a["pending_question"],
    )
    save_socratic_conversation(
        db_path, client_b, "keyB", b["problem_text"], b["language"], b["conversation"], b["pending_question"],
    )

    assert list(load_socratic_conversations(db_path, client_a).keys()) == ["keyA"]
    assert list(load_socratic_conversations(db_path, client_b).keys()) == ["keyB"]


def test_load_socratic_conversations_missing_db_returns_empty(tmp_path):
    assert load_socratic_conversations(str(tmp_path / "does_not_exist.db"), "someone") == {}


def test_save_socratic_conversation_missing_required_key_fails_gracefully(tmp_path):
    db_path = str(tmp_path / "test.db")
    init_db(db_path)
    assert save_socratic_conversation(db_path, new_client_id(), "key1", "", "Python", [], "Q?") is True


def test_delete_client_socratic_clears_only_that_client(tmp_path):
    db_path = str(tmp_path / "test.db")
    init_db(db_path)
    client_a, client_b = new_client_id(), new_client_id()

    a = _conversation()
    b = _conversation(problem_text="Different problem")
    save_socratic_conversation(
        db_path, client_a, "keyA", a["problem_text"], a["language"], a["conversation"], a["pending_question"],
    )
    save_socratic_conversation(
        db_path, client_b, "keyB", b["problem_text"], b["language"], b["conversation"], b["pending_question"],
    )

    assert delete_client_socratic(db_path, client_a) is True
    assert load_socratic_conversations(db_path, client_a) == {}
    assert list(load_socratic_conversations(db_path, client_b).keys()) == ["keyB"]


def test_save_lesson_missing_required_key_fails_gracefully(tmp_path):
    db_path = str(tmp_path / "test.db")
    init_db(db_path)
    # Missing "title" -- should return False, not raise a KeyError up to the caller.
    assert save_lesson_to_db(db_path, new_client_id(), {"takeaway": "t", "tags": [], "language": "Python"}) is False


def test_get_db_path_respects_env_var(monkeypatch):
    monkeypatch.setenv(DB_ENV_VAR, "/custom/path/data.db")
    assert get_db_path() == "/custom/path/data.db"


def test_get_db_path_defaults_next_to_module(monkeypatch):
    monkeypatch.delenv(DB_ENV_VAR, raising=False)
    path = get_db_path()
    assert path.endswith("codeunfold_data.db")
