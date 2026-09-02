"""Best-effort persistence for saved lessons, problem history, and
in-progress Socratic exchanges, surviving a tab refresh.

Previously `lessons_memory` lived only in `st.session_state` and was gone
the moment the tab refreshed. This module adds a lightweight persistence
layer using `sqlite3` (Python stdlib -- no new dependency) keyed by a
`client_id` stored in the page's URL query params. The same store now
also persists problem history (the sidebar's restore list) and in-flight
Socratic exchanges, so a refresh doesn't lose work-in-progress either.

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
import time
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
    """Creates the lessons, problem_history, and socratic_conversations
    tables if needed. Returns False (not raises) on any filesystem/DB
    error, so callers can degrade to session-only mode.

    Adding tables is non-destructive (CREATE TABLE IF NOT EXISTS): a
    database created before problem history existed gains the new tables
    on first run and keeps its lessons untouched -- no migration needed.
    The UNIQUE(client_id, problem_key) constraints are what make the
    per-problem upserts in save_problem_history/save_socratic_conversation
    work (a problem worked on twice updates its one row in place, exactly
    like the in-memory history dict overwrites in problem_history.py).
    """
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
            conn.execute(
                """CREATE TABLE IF NOT EXISTS problem_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    client_id TEXT NOT NULL,
                    problem_key TEXT NOT NULL,
                    problem_text TEXT NOT NULL,
                    language TEXT NOT NULL,
                    title TEXT NOT NULL,
                    current_solution TEXT,
                    current_hints TEXT,
                    raw_code TEXT,
                    verification TEXT,
                    attempt_errors TEXT,
                    timestamp REAL NOT NULL,
                    UNIQUE (client_id, problem_key)
                )"""
            )
            conn.execute(
                """CREATE TABLE IF NOT EXISTS socratic_conversations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    client_id TEXT NOT NULL,
                    problem_key TEXT NOT NULL,
                    problem_text TEXT NOT NULL,
                    language TEXT NOT NULL,
                    conversation TEXT NOT NULL,
                    pending_question TEXT,
                    timestamp REAL NOT NULL,
                    UNIQUE (client_id, problem_key)
                )"""
            )
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


def save_problem_history(db_path: str, client_id: str, key: str, snapshot: dict) -> bool:
    """Persists one problem-history snapshot, keyed by problem_key.

    `snapshot` is exactly the dict problem_history.build_snapshot()
    produces (see problem_history.py), so the same record can be written
    to disk and later read back into st.session_state without reshaping
    anything. The verification dict and attempt_errors list are JSON-
    encoded; both are None/empty-safe. Upsert semantics (UNIQUE on
    (client_id, problem_key)) mirror the in-memory history dict's
    overwrite-in-place behavior: a problem worked on twice keeps one row,
    updated to the latest state. Returns False (not raises) on failure.
    """
    try:
        verification = json.dumps(snapshot["verification"]) if snapshot.get("verification") is not None else None
        attempt_errors = json.dumps(snapshot.get("attempt_errors") or [])
        with _connect(db_path) as conn:
            conn.execute(
                """INSERT INTO problem_history
                   (client_id, problem_key, problem_text, language, title,
                    current_solution, current_hints, raw_code, verification,
                    attempt_errors, timestamp)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(client_id, problem_key) DO UPDATE SET
                     problem_text = excluded.problem_text,
                     language = excluded.language,
                     title = excluded.title,
                     current_solution = excluded.current_solution,
                     current_hints = excluded.current_hints,
                     raw_code = excluded.raw_code,
                     verification = excluded.verification,
                     attempt_errors = excluded.attempt_errors,
                     timestamp = excluded.timestamp""",
                (
                    client_id, key,
                    snapshot["problem_text"], snapshot.get("language", ""),
                    snapshot.get("title", ""), snapshot.get("current_solution"),
                    snapshot.get("current_hints"), snapshot.get("raw_code", ""),
                    verification, attempt_errors,
                    snapshot.get("timestamp", time.time()),
                ),
            )
            conn.commit()
        return True
    except (sqlite3.Error, OSError, KeyError):
        return False


def load_problem_history(db_path: str, client_id: str) -> dict:
    """Loads all persisted history for a client as a dict keyed by
    problem_key, newest last (chronological, matching the in-memory
    dict's insertion order).

    Each value is shaped exactly like problem_history.build_snapshot()
    output (including the timestamp), so the loaded dict can be handed to
    cap_history()/recent_entries() and restored from, unchanged. A row
    whose JSON columns are corrupt is skipped rather than failing the
    whole load (defense against a partially-written row). Returns {}
    (not raises) on any DB error -- indistinguishable from "no history
    yet", which is the correct degrade-gracefully behavior.
    """
    try:
        with _connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT problem_key, problem_text, language, title, current_solution, "
                "current_hints, raw_code, verification, attempt_errors, timestamp "
                "FROM problem_history WHERE client_id = ? ORDER BY timestamp ASC",
                (client_id,),
            ).fetchall()
    except (sqlite3.Error, OSError):
        return {}

    history = {}
    for row in rows:
        try:
            verification = json.loads(row["verification"]) if row["verification"] is not None else None
            attempt_errors = json.loads(row["attempt_errors"]) if row["attempt_errors"] else []
        except json.JSONDecodeError:
            continue
        history[row["problem_key"]] = {
            "problem_text": row["problem_text"],
            "language": row["language"],
            "current_solution": row["current_solution"],
            "current_hints": row["current_hints"],
            "raw_code": row["raw_code"],
            "verification": verification,
            "attempt_errors": attempt_errors,
            "title": row["title"],
            "timestamp": row["timestamp"],
        }
    return history


def delete_client_history(db_path: str, client_id: str) -> bool:
    """Clears all problem history for a client (backs the sidebar
    'Forget my history' control, mirroring delete_client_lessons)."""
    try:
        with _connect(db_path) as conn:
            conn.execute("DELETE FROM problem_history WHERE client_id = ?", (client_id,))
            conn.commit()
        return True
    except (sqlite3.Error, OSError):
        return False


def save_socratic_conversation(
    db_path: str, client_id: str, key: str, problem_text: str,
    language: str, conversation: list, pending_question,
) -> bool:
    """Persists one in-progress Socratic exchange, keyed by problem_key.

    `conversation` is the list of {"question", "answer", "feedback"} dicts
    held in st.session_state.socratic_conversation, JSON-encoded here so a
    tab refresh can resume the exchange instead of losing it (see
    main.py's bootstrap restore logic). Upsert semantics match the
    in-memory behavior: one row per problem, updated in place. Returns
    False (not raises) on failure.
    """
    try:
        with _connect(db_path) as conn:
            conn.execute(
                """INSERT INTO socratic_conversations
                   (client_id, problem_key, problem_text, language,
                    conversation, pending_question, timestamp)
                   VALUES (?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(client_id, problem_key) DO UPDATE SET
                     problem_text = excluded.problem_text,
                     language = excluded.language,
                     conversation = excluded.conversation,
                     pending_question = excluded.pending_question,
                     timestamp = excluded.timestamp""",
                (
                    client_id, key, problem_text, language,
                    json.dumps(conversation or []),
                    pending_question, time.time(),
                ),
            )
            conn.commit()
        return True
    except (sqlite3.Error, OSError):
        return False


def load_socratic_conversations(db_path: str, client_id: str) -> dict:
    """Loads all persisted Socratic exchanges for a client as a dict
    keyed by problem_key, newest last (chronological). Each value is
    {"conversation": [...], "pending_question": str|None, "problem_text",
    "language", "timestamp"} -- enough for main.py to decide whether to
    resume an exchange after a refresh. Returns {} (not raises) on any
    DB error, indistinguishable from "no in-progress exchanges".
    """
    try:
        with _connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT problem_key, problem_text, language, conversation, "
                "pending_question, timestamp "
                "FROM socratic_conversations WHERE client_id = ? ORDER BY timestamp ASC",
                (client_id,),
            ).fetchall()
    except (sqlite3.Error, OSError):
        return {}

    conversations = {}
    for row in rows:
        try:
            conversation = json.loads(row["conversation"])
        except json.JSONDecodeError:
            continue
        conversations[row["problem_key"]] = {
            "conversation": conversation,
            "pending_question": row["pending_question"],
            "problem_text": row["problem_text"],
            "language": row["language"],
            "timestamp": row["timestamp"],
        }
    return conversations


def delete_client_socratic(db_path: str, client_id: str) -> bool:
    """Clears all persisted Socratic exchanges for a client."""
    try:
        with _connect(db_path) as conn:
            conn.execute("DELETE FROM socratic_conversations WHERE client_id = ?", (client_id,))
            conn.commit()
        return True
    except (sqlite3.Error, OSError):
        return False


def new_client_id() -> str:
    return uuid.uuid4().hex[:16]
