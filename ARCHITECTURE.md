# Architecture

CodeUnfold is a single-process Streamlit app with no database and no
background workers. Every request is a full script re-execution of
`main.py` (Streamlit's execution model), reading and writing
`st.session_state` to persist data across reruns within one browser
session.

## Module map

| Module | Responsibility | Depends on Streamlit? |
| :--- | :--- | :--- |
| `main.py` | Widget layout, button handlers, orchestration. The only place render order matters. | Yes — this is the script Streamlit executes. |
| `ai_client.py` | Provider routing (Gemini → Groq fallback), all prompt builders, input sanitization. | Only for `st.secrets`/`st.cache_resource` on the client factory. |
| `response_parser.py` | Pure functions: pull `<tag>...</tag>` sections and fenced code blocks out of raw LLM text. | No. |
| `code_verifier.py` | Extracts examples from problem text, executes Python/JS solutions against them in a subprocess. | No. |
| `lesson_memory.py` | Topic-tags saved lessons via keyword matching; picks the most relevant ones for a given problem. | No. |
| `rate_limiter.py` | `RateLimiter` (per-session sliding window) and `GlobalRateLimiter` (process-wide daily budget). | No — plain Python classes. |
| `app_helpers.py` | Glue: rate-limit checks, server-side length caps, error-message categorization, lesson-context assembly. | Yes, via `st.session_state`/`st.cache_resource`. |
| `styles.py` | Static + theme-dependent CSS strings. | No — returns strings; `main.py` calls `st.markdown()` on them. |
| `logger.py` | App-wide logger; console always, file best-effort (see Known Limitations). | No. |

The split between "pure logic" modules (`response_parser`, `code_verifier`,
`lesson_memory`, `rate_limiter`) and "Streamlit-aware" modules (`main.py`,
`app_helpers.py`) is deliberate: everything in the pure-logic group is
unit-testable with plain `pytest`, no Streamlit runtime required. Only
`main.py`'s widget/button flow needs the heavier `AppTest` integration
harness (see `tests/test_app_integration.py`).

## Why `main.py` isn't split further

Streamlit scripts run top-to-bottom on every interaction; widget calls
must execute in the same relative order every run for `st.session_state`
keys to stay attached to the right widgets. That makes `main.py`'s
control flow — form definition → button click → conditional AI call →
rerun → tabbed display — inherently order-sensitive in a way that doesn't
factor cleanly into independent `ui.py` / `handlers.py` modules without a
larger rewrite (e.g. moving to a callback-registration pattern). The
current split pulls out everything that *can* be separated safely
(styling, stateless helpers, all prompt/parsing/verification logic) and
leaves the order-sensitive parts in one file, rather than force a split
that would risk subtle session-state bugs for a marginal readability win.

## Data flow: solving a problem

1. User pastes a problem into `_problem_widget` (a Streamlit text_area) and clicks **Reveal Solution**.
2. `main.py` re-truncates the input server-side (`app_helpers._enforce_server_side_length`) regardless of what the widget's client-side `max_chars` allowed.
3. Two rate-limit gates run: `RateLimiter` (per-session, resets each session) and `GlobalRateLimiter` (process-wide daily budget, survives session resets — see `rate_limiter.py`'s docstrings for why both exist).
4. `ai_client.build_solve_prompt()` builds the prompt, sanitizing the problem text against prompt injection (`_sanitize_input`) and injecting relevant saved lessons (`app_helpers._get_lessons_context`, backed by `lesson_memory.select_relevant_lessons`).
5. `ai_client.call_ai()` tries the user's own Gemini key (if provided) → the app's default Gemini key → Groq as a last resort, in that order, catching provider-specific rate-limit/quota errors along the way.
6. `response_parser.extract_code_block()` and `extract_solution_sections()` pull the code and the seven required tags out of the raw response.
7. `code_verifier.verify_solution()` actually runs the extracted Python/JS code against an example parsed from the problem text, in a timeout-bounded subprocess — this is what backs the ✅/❌ badge, replacing the model's own self-reported "I traced 2 edge cases" claim.
8. The tabbed UI renders; the student can save a takeaway to `lessons_memory` (tagged via `lesson_memory.build_lesson`) for future prompts to reference.

## Data flow: Socratic hint mode

Instead of steps 4–6 above producing the full hint breakdown in one call,
Socratic mode (`ai_client.build_socratic_question_prompt` /
`build_socratic_feedback_prompt`) asks one diagnostic question, waits for
the student's typed answer (also sanitized before being embedded in the
next prompt), and after `SOCRATIC_MAX_TURNS` rounds converges into the
same `<intuition>/<walkthrough>/<pseudocode>` tag set the standard hint
prompt produces — so the display code doesn't need a separate renderer,
just the same `response_parser.extract_hint_sections()` it already had.

## Known limitations

- **Single-instance rate limiting.** `GlobalRateLimiter` guards one
  running process. Scaling to multiple instances behind a load balancer
  would give each instance its own independent budget.
- **Ephemeral memory.** `lessons_memory` lives in `st.session_state` —
  gone on tab close/refresh. No database, by design (see README for the
  tradeoff rationale).
- **`code_verifier.py` is not a hardened sandbox.** It's a
  timeout-bounded, best-effort-network-disabled subprocess check meant
  to catch obviously wrong output, not a security boundary for executing
  arbitrary untrusted code at scale.
- **Best-effort logging.** `logger.py` falls back to console-only
  logging if the filesystem is read-only (some container platforms) —
  see the module docstring.

See `SECURITY.md` for the threat model this app is (and isn't) designed for.
