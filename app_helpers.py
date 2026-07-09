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
MAX_PROBLEM_CHARS = 5000
MAX_CODE_CHARS = 5000

# Process-wide daily budget, shared across every visitor session on this
# instance (see rate_limiter.GlobalRateLimiter for why this -- and not just
# the per-session RateLimiter used elsewhere -- is what actually protects
# the shared Groq/Gemini free-tier keys). Kept with headroom under the
# tightest real cap in the fallback chain (Groq 70B, ~1,000 requests/day).
GLOBAL_DAILY_CALL_BUDGET = 800

SESSION_AI_CALL_LIMIT = 5


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
    err = str(e).lower()
    if "rate" in err or "429" in err or "resource_exhausted" in err:
        st.error("⏳ Rate limit reached. Please wait a moment and try again.")
    elif "503" in err or "unavailable" in err or "busy" in err:
        st.error("🔄 AI is temporarily under high load. Please try again in 10–15 seconds.")
    elif "timeout" in err:
        st.error("⏱️ Request timed out. Please try again.")
    elif "api" in err or "key" in err or "auth" in err:
        st.error("🔑 API key issue. Please check your API keys in the sidebar.")
    else:
        st.error("❌ Something went wrong. Please try again.")
        log.error(f"{context}: {e}")
