# Contributing to CodeUnfold

Thanks for considering a contribution. This doc is for human contributors;
if you're working with an AI coding agent (Claude Code, Cursor, etc.),
point it at [`AGENTS.md`](./AGENTS.md) instead (or in addition -- it has
setup steps and a list of hard rules that grew out of real bugs).

## Getting set up

```bash
git clone https://github.com/mzaman001/CodeUnfold.git
cd CodeUnfold
pip install -r requirements.txt -r requirements-dev.txt
cp .env.example .env   # then fill in at least one API key
streamlit run main.py
```

Requires Python 3.10+. Node.js 20+ if you want to work on JavaScript
solution verification (`code_verifier.py`'s `_run_js_example`).

## Before opening a PR

Run the same checks CI runs:

```bash
python3 -m py_compile main.py ai_client.py rate_limiter.py response_parser.py \
    code_verifier.py logger.py app_helpers.py styles.py lesson_memory.py persistence.py
ruff check .
pytest -v
```

If you touched `main.py`'s widget layout or session-state handling, also
do a live boot check -- several real bugs in this project's history only
surfaced when the app actually ran under `streamlit run`, not in unit
tests:

```bash
streamlit run main.py
# open the printed local URL and click through the flow you changed
```

## What a good PR looks like

- **Tests included.** If you fix a bug, add a test that would have
  caught it (see `tests/` for the pattern -- most existing tests are
  named after the specific bug they guard against, e.g.
  `test_verify_solution_survives_missing_resource_module`). If you add a
  feature, add tests for its logic, not just a smoke test that it
  doesn't crash.
- **Docstrings explain *why*, not just *what*.** This codebase leans on
  that pattern, especially for anything that looks simplifiable but
  isn't (e.g. why there are two rate limiters, why a truncation
  boundary was moved). It saves the next person from "simplifying"
  something back into a bug that already shipped once.
- **Small and focused.** A PR that fixes one bug or adds one feature is
  much easier to review than one that reorganizes three files while
  also fixing a typo.

## Where things live

See [`ARCHITECTURE.md`](./ARCHITECTURE.md) for the module map. Quick
pointers:
- Prompt text and provider routing → `ai_client.py`
- Parsing AI responses → `response_parser.py`
- Running/checking generated code → `code_verifier.py`
- Rate limiting → `rate_limiter.py`
- Saved-lesson tagging/relevance → `lesson_memory.py`
- Cross-refresh lesson storage → `persistence.py`
- Widget layout and button handlers → `main.py`
- Everything else `main.py` needs that isn't UI-order-sensitive → `app_helpers.py`

## Reporting bugs

Open a GitHub issue with: what you did, what you expected, what
happened instead, and (if it's not obvious) your Python/Node version and
OS. For anything security-sensitive, see
[`SECURITY.md`](./SECURITY.md#reporting-a-vulnerability) instead of
filing a public issue.

## Code of conduct

Be respectful, assume good faith, keep discussion focused on the code.
