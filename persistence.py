"""Best-effort persistence for saved lessons, surviving a tab refresh.

Previously `lessons_memory` lived only in `st.session_state` and was gone
the moment the tab refreshed. This module adds a lightweight persistence
layer using `sqlite3` (Python stdlib -- no new dependency) keyed by a
`client_id` stored in the page's URL query params.

Scope, stated plainly (see README/SECURITY.md for the user-facing
version of this):
- This is NOT an account system. There's no login, no password, no
  cross-device sync. The "identity" is just a random ID living in the
  URL. Bookmark the URL (with its `?cid=...`) to come back to the same
  lessons; open the app in a fresh tab/browser without that URL and
  you start empty, same as before this feature existed.
- This is single-instance, file-based storage. It does not survive a
  redeploy that wipes the filesystem (e.g. most container platforms'
  ephemeral storage), and it does not work if you scale to multiple
  app instances behind a load balancer (each instance would have its
  own separate DB file).
- It is best-effort: on a read-only filesystem (some container
  platforms), persistence silently degrades to session-only (the old
  behavior) rather than crashing the app -- same guard pattern as
  `logger.py`.
"""
import json
import os
import sqlite3
import uuid
from contextlib import contextmanager

DB_ENV_VAR = "CODEUNFOLD_DB_PATH"
DEFAULT_DB_FILENAME = "codeunfold_data.db"


def get_db_path() -> str:
    """Resolves the SQLite file path: env var override, else next to this module."""
    override = os.environ.get(DB_ENV_VAR)
    if override:
        return override
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), DEFAULT_DB_FILENAME)


@contextmanager
def _connect(db_path: str):
    conn = sqlite3.connect(db_path, timeout=5)
    try:
        yield conn
    finally:
        conn.close()


def init_db(db_path: str) -> bool:
    """Creates the lessons table if needed. Returns False (not raises) on
    any filesystem/DB error, so callers can degrade to session-only mode."""
    try:
        with _connect(db_path) as conn:
            conn.execute(
                """CREATE TABLE IF NOT EXISTS lessons (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    client_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    takeaway TEXT NOT NULL,
                    tags TEXT NOT NULL,
                    language TEXT NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )"""
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_lessons_client ON lessons(client_id)")
            conn.commit()
        return True
    except (sqlite3.Error, OSError):
        return False


def save_lesson_to_db(db_path: str, client_id: str, lesson: dict) -> bool:
    """Persists one lesson. Returns False (not raises) on failure."""
    try:
        with _connect(db_path) as conn:
            conn.execute(
                "INSERT INTO lessons (client_id, title, takeaway, tags, language) VALUES (?, ?, ?, ?, ?)",
                (client_id, lesson["title"], lesson["takeaway"], json.dumps(lesson.get("tags", [])), lesson.get("language", "")),
            )
            conn.commit()
        return True
    except (sqlite3.Error, OSError, KeyError):
        return False


def load_lessons_from_db(db_path: str, client_id: str, limit: int = 50) -> list:
    """Loads saved lessons for a client, most recent last (chronological).
    Returns an empty list (not raises) on any failure -- an empty list is
    indistinguishable from "no lessons saved yet", which is the correct
    degrade-gracefully behavior here.
    """
    try:
        with _connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT title, takeaway, tags, language FROM lessons WHERE client_id = ? ORDER BY id ASC LIMIT ?",
                (client_id, limit),
            ).fetchall()
        return [
            {"title": r["title"], "takeaway": r["takeaway"], "tags": json.loads(r["tags"]), "language": r["language"]}
            for r in rows
        ]
    except (sqlite3.Error, OSError, json.JSONDecodeError):
        return []


def delete_client_lessons(db_path: str, client_id: str) -> bool:
    """Clears all lessons for a client (used by the sidebar 'Forget my saved lessons' control)."""
    try:
        with _connect(db_path) as conn:
            conn.execute("DELETE FROM lessons WHERE client_id = ?", (client_id,))
            conn.commit()
        return True
    except (sqlite3.Error, OSError):
        return False


def delete_last_lesson(db_path: str, client_id: str) -> bool:
    """Deletes the most recently saved lesson for a client (backs the
    existing "Undo (Remove from Memory)" button, so Undo actually removes
    the persisted copy too, not just the in-memory session list)."""
    try:
        with _connect(db_path) as conn:
            conn.execute(
                "DELETE FROM lessons WHERE id = (SELECT MAX(id) FROM lessons WHERE client_id = ?)",
                (client_id,),
            )
            conn.commit()
        return True
    except (sqlite3.Error, OSError):
        return False


def new_client_id() -> str:
    return uuid.uuid4().hex[:16]
