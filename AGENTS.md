# AGENTS.md

Instructions for AI coding agents (Claude Code, Cursor, Copilot Workspace,
etc.) working in this repository. Human contributors: this is also a
reasonable map of the codebase's conventions.

## Before making changes

1. Read `ARCHITECTURE.md` for the module map and why `main.py` isn't
   split further than it is.
2. Read `SECURITY.md` before touching `ai_client.py`'s sanitization,
   `code_verifier.py`'s execution sandbox, or `rate_limiter.py` — these
   three exist specifically to hold lines that are easy to accidentally
   loosen while "cleaning up" code.

## Setup

```bash
pip install -r requirements.txt -r requirements-dev.txt
```

## Running checks (do this before considering any change done)

```bash
python3 -m py_compile main.py ai_client.py rate_limiter.py response_parser.py \
    code_verifier.py logger.py app_helpers.py styles.py lesson_memory.py
ruff check .
pytest -v
```

All three must pass. `pytest` includes `tests/test_app_integration.py`,
which runs the *actual* `main.py` via Streamlit's `AppTest` framework —
this is the test layer that catches Streamlit runtime/widget-lifecycle
bugs (session-state/widget-key conflicts, etc.) that pure unit tests on
extracted functions cannot. If you touch `main.py`'s widget or
session-state code, this is the suite that matters most.

If you can start the app, also do a live boot check — several real bugs
in this codebase's history only showed up when the app actually ran
under `streamlit run`, not at import time or in unit tests:

```bash
GROQ_API_KEY=fake GEMINI_API_KEY=fake timeout 8 streamlit run main.py \
    --server.headless true --server.port 8501
# then curl http://localhost:8501 and check for a 200 with no traceback in the logs
```

## Hard rules

- **Never write to `st.session_state[key]` after a widget with that
  same `key` has already been instantiated in the same script run.**
  Streamlit raises `StreamlitAPIException`. This exact bug shipped once
  (see `tests/test_app_integration.py::test_solve_button_does_not_raise_streamlit_api_exception`,
  which reproduces it) — if you need to cap/transform a widget-bound
  value, do it at the read site (see `app_helpers._get_user_code_capped`
  for the pattern), never by reassigning the widget's own key.
- **Every new piece of user-controlled text that reaches a prompt must
  go through `ai_client._sanitize_input()`.** This includes anything
  pasted, typed, or uploaded by the user — not just the problem
  statement. See `SECURITY.md` §1 for the current list of sanitized
  inputs; extend it, don't work around it.
- **Don't add an unguarded `import resource`, unguarded `FileHandler`,
  or anything else OS-specific at module import time or in code that
  runs in `code_verifier.py`'s subprocess harness.** `resource` doesn't
  exist on Windows; an unguarded import previously crashed every Python
  verification on that platform. Wrap platform-specific imports/calls in
  `try/except` with a documented fallback.
- **Anything in `code_verifier.py` stays best-effort and says so.**
  Don't upgrade its docstring/comments to imply it's a hardened sandbox
  without actually making it one (see `SECURITY.md` §4 for what that
  would require).
- **Pure-logic modules (`response_parser.py`, `code_verifier.py`,
  `lesson_memory.py`, `rate_limiter.py`) must not import `streamlit`.**
  That's what keeps them plain-`pytest`-testable without the `AppTest`
  harness. If a function needs `st.session_state`, it belongs in
  `main.py` or `app_helpers.py`, not these.
- **New prompt builders in `ai_client.py` need a matching test in
  `tests/test_ai_client.py`** asserting the required output tags are
  present and that any user-controlled parameter is sanitized. Follow
  the existing tests as a template — they were written specifically to
  catch the "forgot to sanitize a new field" class of bug.
- **Don't reintroduce dead session-state keys.** This codebase has
  twice accumulated state that's written but never read (`_sync_problem`,
  `execution_output`, `last_saved_lesson_text/id` — all removed). If you
  add a session-state key, make sure something actually reads it, or
  don't add it.

## Style

- `ruff check .` is the source of truth; there's no separate style
  guide. If ruff is silent, the style is fine.
- Docstrings/comments in this codebase tend to explain *why*, not just
  *what* — especially around anything that looks like it could be
  simplified but isn't (e.g. why two rate limiters exist, why `main.py`
  isn't split further). Keep that pattern; a future agent (possibly you,
  in a different context window) will thank you.
