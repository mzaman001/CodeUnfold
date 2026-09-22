# CLAUDE.md — CodeUnfold (Socratic LeetCode Tutor)

Single source of truth for Claude Code, Antigravity, and OpenCode in `CodeUnfold`.

## Architecture & Stack
- **Framework**: Streamlit (`main.py`, `app_helpers.py`, `styles.py`)
- **Language**: Python 3.13 / 3.10+
- **Persistence**: SQLite (`codeunfold_data.db`, `persistence.py`, `problem_history.py`, `lesson_memory.py`, `progress_stats.py`)
- **LLM Backends**: Groq (Primary) + Google Gemini (Fallback)
- **Security & Sandboxing**: `code_verifier.py`, `rate_limiter.py`, `response_parser.py` (Strict XML parsing & isolated tags)

## Build, Run & Test Commands
- **Environment**: Use project `.venv` (`.\.venv\Scripts\python.exe` or activate `.venv`)
- **Run App**: `streamlit run main.py`
- **Run All Tests**: `pytest -v` (or `.\.venv\Scripts\pytest.exe -v`)
- **Lint & Format Check**: `ruff check .`
- **Security & Vulnerability Audit**: `pip-audit` (PyPA security scanner)
- **Test Coverage**: `pytest --cov=. --cov-report=term`

## Engineering Invariants & Karpathy Guardrails
1. **Strict XML Boundaries**: User input must always be sanitized in XML envelopes (`<user_problem>`, `<error_report>`) before sending to LLM.
2. **Socratic Guardrail**: Never output full code solutions on the first hint round. Guide the user step-by-step through algorithmic reasoning.
3. **Verified Execution**: Automated test execution in `code_verifier.py` must stay bounded by timeout and avoid unsafe shell execution.
4. **No Destructive DB Migrations**: Preserve existing SQLite schema and user history tables in `codeunfold_data.db`.
5. **Always Verify**: Run `pytest -v`, `pip-audit`, and `ruff check .` before declaring tasks complete.
