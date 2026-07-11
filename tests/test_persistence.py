import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from persistence import (
    init_db, save_lesson_to_db, load_lessons_from_db,
    delete_client_lessons, delete_last_lesson, new_client_id, get_db_path, DB_ENV_VAR,
)


def test_new_client_id_is_unique_and_short():
    a, b = new_client_id(), new_client_id()
    assert a != b
    assert len(a) == 16


def test_init_db_creates_table(tmp_path):
    db_path = str(tmp_path / "test.db")
    assert init_db(db_path) is True
    assert os.path.exists(db_path)


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
