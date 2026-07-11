"""Stateless-ish helper functions shared across main.py's button handlers.

Split out of main.py purely to shrink the main script file and group
related concerns (rate limiting, input-length enforcement, error display,
lesson-context retrieval) together. Everything here still reads/writes
`st.session_state` the same way it would from main.py directly -- Streamlit
session state is keyed per-session at the framework level, not per-module,
so moving these functions here changes nothing about their behavior.

Function names keep their leading underscore from main.py's original
in-file versions (a convention marking "internal to this app", not a
privacy mechanism Python enforces) so every call site in main.py could be
updated by import alone, without touching call-site code.
"""
import streamlit as st

from rate_limiter import GlobalRateLimiter
from lesson_memory import select_relevant_lessons, format_lessons_context
from logger import log

# Server-side hard caps. The Streamlit widgets also set `max_chars`, but
# that's a client-side widget property only -- a scripted client talking
# to the websocket directly can send an arbitrarily long value regardless
# of what the widget enforces in a browser. These constants are the real
# gate, checked again on every submit.
#
# 15000 chars comfortably covers even long LeetCode problems (multiple
# examples, constraints, starter code) while staying trivial relative to
# both Groq Llama 3.3 70B's 128K-token context and Gemini's much larger
# one -- the old 5000-char cap was tight enough to truncate real problems
# with no warning shown to the user (see MAX_PROBLEM_CHARS usage in
# main.py for where the warning now fires).
MAX_PROBLEM_CHARS = 15000
MAX_CODE_CHARS = 15000

# Process-wide daily budget, shared across every visitor session on this
# instance (see rate_limiter.GlobalRateLimiter for why this -- and not just
# the per-session RateLimiter used elsewhere -- is what actually protects
# the shared Groq/Gemini free-tier keys). Kept with headroom under the
# tightest real cap in the fallback chain (Groq 70B, ~1,000 requests/day).
GLOBAL_DAILY_CALL_BUDGET = 800

SESSION_AI_CALL_LIMIT = 5

# FIFO cap on saved lessons per session. Without this, a long multi-hour
# session could accumulate an unbounded list -- each entry holds a full
# takeaway string, and select_relevant_lessons() already bounds how many
# get injected into any single prompt (max_lessons=5), but the underlying
# list itself was previously allowed to grow without limit.
MAX_LESSONS_IN_MEMORY = 50

# How many of the most recent fix-attempt errors to keep feeding back into
# the fix prompt. The old cap of 3 meant that after a 4th+ fix attempt,
# the model no longer saw errors #1-#2 at all and could re-suggest a fix
# that had already failed for a reason it could no longer see. Raised to
# 6 -- still bounded (so a very long debugging session doesn't grow the
# prompt unboundedly), but gives the model enough history to actually
# avoid repeating itself on harder bugs.
MAX_ATTEMPT_ERRORS = 6


@st.cache_resource
def get_global_limiter() -> GlobalRateLimiter:
    return GlobalRateLimiter(daily_budget=GLOBAL_DAILY_CALL_BUDGET)


def _enforce_server_side_length(text: str, max_chars: int) -> str:
    """Truncates on the server regardless of what the client widget sent."""
    if text and len(text) > max_chars:
        return text[:max_chars]
    return text


def _get_user_code_capped() -> str:
    """Reads `user_code` with the server-side length cap applied.

    Deliberately does NOT write back into `st.session_state.user_code` --
    that key belongs to the code-editor widget, and Streamlit forbids
    setting a widget-owned session_state key after the widget has already
    been instantiated in the same run (raises StreamlitAPIException). The
    cap is applied here, at every read, instead.
    """
    return _enforce_server_side_length(st.session_state.get("user_code", ""), MAX_CODE_CHARS)


def _check_session_limit(user_key: str = None) -> bool:
    if user_key:
        return True  # Unlimited if they provide their own key
    return st.session_state.get("session_ai_calls", 0) < SESSION_AI_CALL_LIMIT


def _increment_session_calls():
    st.session_state.session_ai_calls = st.session_state.get("session_ai_calls", 0) + 1


def _show_session_limit_warning(user_key: str = None):
    if user_key:
        return
    used = st.session_state.get("session_ai_calls", 0)
    remaining = SESSION_AI_CALL_LIMIT - used
    if remaining <= 2:
        st.info(
            f"💡 **{remaining} free AI call{'s' if remaining != 1 else ''} remaining** this session. "
            "Add your own free Gemini API key in ⚙️ **Settings** (sidebar) for unlimited access."
        )


def _check_global_limit(user_key: str = None) -> bool:
    """The real, shared-quota guard. A user's own key bypasses the shared
    budget entirely since it doesn't draw on this app's Groq/Gemini keys.
    See rate_limiter.GlobalRateLimiter for why this exists alongside (not
    instead of) the per-session RateLimiter used elsewhere.
    """
    if user_key:
        return True
    return get_global_limiter().allow()


def check_and_consume_rate_limits(user_key: str = None):
    """The single, consistent rate-limit gate for every AI-call site.

    Replaces what used to be three separately-ordered, separately-worded
    checks scattered across each button handler (hint, solve, fix loop,
    Socratic question, Socratic answer, Socratic skip) -- which had
    drifted out of sync with each other. Notably, the Socratic "skip to
    full hints" button used to check only the sliding-window and global
    limiters, silently skipping the per-session 5-free-calls cap that
    every other AI-call site enforced -- a real (if minor) way to bypass
    the shared free-tier budget. Every call site should now go through
    this one function instead of reimplementing the check sequence.

    Peeks every applicable limit (session cap, sliding window, global
    daily budget) with non-mutating `would_allow()` checks *before*
    consuming any of them. Without this ordering, a request that passed
    the cheap per-session sliding-window check but was then blocked by
    the global daily budget would still have consumed one of the
    session's 15-per-60s slots for a request that never actually went
    through -- wasting part of a legitimate user's short-term budget for
    nothing.

    Returns (allowed: bool, error_message: str). Only mutates state
    (consumes a slot from each limiter, increments the session call
    counter) when `allowed` is True.
    """
    if user_key:
        return True, ""  # BYOK bypasses every shared-quota limit entirely

    if not _check_session_limit():
        return False, (
            f"💡 You've used all {SESSION_AI_CALL_LIMIT} free AI calls for this session. "
            "Add your own free Gemini API key in ⚙️ **Settings** in the sidebar for unlimited access."
        )

    if not st.session_state.ai_limiter.would_allow():
        return False, "⏳ Too many requests! Please wait a moment."

    if not get_global_limiter().would_allow():
        return False, (
            "🛑 This app has hit its shared daily AI quota (protecting the free Groq/Gemini keys "
            "everyone shares). Add your own free Gemini API key in ⚙️ **Settings** for unlimited access, "
            "or try again after the daily reset."
        )

    # All three checks passed -- only now do we actually consume budget.
    st.session_state.ai_limiter.allow()
    get_global_limiter().allow()
    _increment_session_calls()
    return True, ""


def _get_lessons_context(problem_text: str = "") -> str:
    """Retrieves the most relevant saved lessons for the given problem.

    Prioritizes lessons whose inferred topic tags overlap with the
    current problem (e.g. don't inject a "Sliding Window" lesson while
    solving a graph problem) and falls back to recency if nothing
    overlaps. See lesson_memory.py for the tagging/selection logic.
    """
    lessons = st.session_state.get("lessons_memory", [])
    relevant = select_relevant_lessons(lessons, problem_text, max_lessons=5)
    return format_lessons_context(relevant)


def _show_error(e: Exception, context: str = ""):
    """Classifies an exception into a user-facing message.

    Classification uses two signals, in order:
    1. The exception's type name (e.g. "RateLimitError", "PermissionDeniedError")
       -- this is far less prone to false positives than message content,
       since SDKs generally name their exception classes consistently.
    2. Specific message markers (HTTP status codes, well-known error
       codes) rather than bare words like "key" or "api", which are
       common enough in unrelated error text to cause misclassification
       -- e.g. a rate-limit error whose message happens to mention
       "API key rate limit exceeded" would previously have been caught
       by the broad `"key" in err` check and shown as an API-key problem
       instead of a rate-limit problem.
    """
    type_name = type(e).__name__.lower()
    err = str(e).lower()

    def matches(type_markers, msg_markers):
        return any(m in type_name for m in type_markers) or any(m in err for m in msg_markers)

    if matches(["ratelimit", "resourceexhausted", "toomanyrequests"], ["rate limit", "429", "resource_exhausted", "resource exhausted"]):
        st.error("⏳ Rate limit reached. Please wait a moment and try again.")
    elif matches(["serviceunavailable", "internalservererror"], [" 503", "unavailable", "high load", "server error", "overloaded", "busy"]):
        st.error("🔄 AI is temporarily under high load. Please try again in 10–15 seconds.")
    elif matches(["timeout", "timeouterror", "deadlineexceeded"], ["timeout", "timed out", "deadline exceeded"]):
        st.error("⏱️ Request timed out. Please try again.")
    elif matches(
        ["permissiondenied", "unauthorized", "authenticationerror", "invalidapikey"],
        ["invalid_api_key", "invalid api key", " 401", " 403", "unauthorized", "authentication failed", "permission_denied", "permission denied"],
    ):
        st.error("🔑 API key issue. Please check your API keys in the sidebar.")
    else:
        st.error("❌ Something went wrong. Please try again.")
        with st.expander("Error details"):
            st.code(str(e)[:500])
        log.error(f"{context}: {e}")
