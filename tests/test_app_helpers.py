import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
import streamlit as st

from rate_limiter import RateLimiter
from app_helpers import (
    MAX_PROBLEM_CHARS, MAX_CODE_CHARS, SESSION_AI_CALL_LIMIT,
    _enforce_server_side_length, _get_user_code_capped,
    _check_session_limit, _increment_session_calls, _show_session_limit_warning,
    _check_global_limit, _get_lessons_context, _show_error,
    check_and_consume_rate_limits, get_global_limiter,
)


@pytest.fixture(autouse=True)
def reset_global_limiter():
    """get_global_limiter() is @st.cache_resource -- process-wide, so its
    internal counter persists across tests unless explicitly cleared."""
    st.cache_resource.clear()
    yield
    st.cache_resource.clear()


@pytest.fixture(autouse=True)
def reset_session_state():
    """app_helpers functions read/write st.session_state directly; reset
    it before each test so tests don't leak state into each other."""
    st.session_state.clear()
    yield
    st.session_state.clear()


# ---------- _enforce_server_side_length ----------

def test_enforce_length_noop_under_limit():
    assert _enforce_server_side_length("short text", 100) == "short text"


def test_enforce_length_truncates_over_limit():
    result = _enforce_server_side_length("x" * 200, 100)
    assert len(result) == 100


def test_enforce_length_handles_empty_string():
    assert _enforce_server_side_length("", 100) == ""


def test_enforce_length_handles_none():
    assert _enforce_server_side_length(None, 100) is None


def test_enforce_length_exact_boundary_not_truncated():
    text = "x" * 100
    assert _enforce_server_side_length(text, 100) == text


def test_max_problem_chars_is_enforced_by_enforce_length():
    text = "x" * (MAX_PROBLEM_CHARS + 1000)
    result = _enforce_server_side_length(text, MAX_PROBLEM_CHARS)
    assert len(result) == MAX_PROBLEM_CHARS


# ---------- _get_user_code_capped ----------

def test_get_user_code_capped_reads_session_state():
    st.session_state["user_code"] = "print('hi')"
    assert _get_user_code_capped() == "print('hi')"


def test_get_user_code_capped_applies_cap():
    st.session_state["user_code"] = "x" * (MAX_CODE_CHARS + 500)
    assert len(_get_user_code_capped()) == MAX_CODE_CHARS


def test_get_user_code_capped_missing_key_returns_empty_string():
    assert _get_user_code_capped() == ""


# ---------- _check_session_limit / _increment_session_calls ----------

def test_check_session_limit_allows_under_cap():
    st.session_state["session_ai_calls"] = 0
    assert _check_session_limit() is True


def test_check_session_limit_blocks_at_cap():
    st.session_state["session_ai_calls"] = SESSION_AI_CALL_LIMIT
    assert _check_session_limit() is False


def test_check_session_limit_bypassed_by_user_key():
    st.session_state["session_ai_calls"] = SESSION_AI_CALL_LIMIT
    assert _check_session_limit(user_key="some-key") is True


def test_increment_session_calls_increments_from_zero():
    st.session_state["session_ai_calls"] = 0
    _increment_session_calls()
    assert st.session_state["session_ai_calls"] == 1


def test_increment_session_calls_handles_missing_key():
    _increment_session_calls()
    assert st.session_state["session_ai_calls"] == 1


def test_session_limit_and_increment_integration():
    st.session_state["session_ai_calls"] = 0
    for _ in range(SESSION_AI_CALL_LIMIT):
        assert _check_session_limit() is True
        _increment_session_calls()
    assert _check_session_limit() is False


def test_show_session_limit_warning_does_not_raise_near_limit():
    st.session_state["session_ai_calls"] = SESSION_AI_CALL_LIMIT - 1
    _show_session_limit_warning()  # must not raise


def test_show_session_limit_warning_skipped_with_user_key():
    st.session_state["session_ai_calls"] = SESSION_AI_CALL_LIMIT
    _show_session_limit_warning(user_key="some-key")  # must not raise, and is a no-op internally


# ---------- _check_global_limit ----------

def test_check_global_limit_allows_by_default():
    assert _check_global_limit() is True


def test_check_global_limit_bypassed_by_user_key():
    # Even if somehow exhausted, a user-supplied key always bypasses the
    # shared-quota guard since it doesn't draw on the app's own keys.
    assert _check_global_limit(user_key="some-key") is True


# ---------- _get_lessons_context ----------

def test_get_lessons_context_empty_when_no_lessons():
    st.session_state["lessons_memory"] = []
    assert _get_lessons_context("some problem") == ""


def test_get_lessons_context_includes_saved_lesson():
    st.session_state["lessons_memory"] = [
        {"title": "Two Sum", "takeaway": "use a hash map", "tags": ["Hash Map"], "language": "Python"}
    ]
    context = _get_lessons_context("a hash map problem")
    assert "Two Sum" in context
    assert "use a hash map" in context


def test_get_lessons_context_missing_key_returns_empty_string():
    assert _get_lessons_context("some problem") == ""


# ---------- _show_error classification (regression tests for W14/B10) ----------

def test_show_error_classifies_plain_rate_limit():
    # Should not raise; visual output isn't asserted (bare-mode Streamlit
    # no-ops UI calls), but the function must not throw.
    _show_error(Exception("429 Too Many Requests"))


def test_show_error_rate_limit_message_mentioning_key_is_not_misclassified_as_api_key_issue():
    """Regression test for B10/W14: an error whose message contains the
    word 'key' (e.g. "API key rate limit exceeded") used to be caught by
    the old broad `"key" in err` check and shown as an API-key problem,
    even though it's actually a rate-limit error. The rate-limit check
    must win because it's checked first AND uses a more specific marker
    ("rate limit") that this message actually contains.
    """
    # We can't directly assert which st.error() branch fired (Streamlit
    # no-ops st.error in bare test mode), so we test the underlying
    # classification logic directly via the same markers _show_error uses.
    import app_helpers
    import inspect
    source = inspect.getsource(app_helpers._show_error)
    # Sanity: the rate-limit branch must be checked before the api/key/auth branch.
    rate_branch_pos = source.index('"⏳ Rate limit reached')
    auth_branch_pos = source.index("🔑 API key issue")
    assert rate_branch_pos < auth_branch_pos


def test_show_error_does_not_use_bare_word_markers_for_auth_branch():
    """Regression test: the auth/key branch's marker list must not contain
    bare substrings like "key", "api", or "auth" (which false-positive on
    almost any error message), only specific markers (401, 403,
    invalid_api_key, etc). Checks the actual marker list passed to
    `matches(...)` for the auth branch, not the whole function source
    (which legitimately discusses the old bug in its docstring).
    """
    import app_helpers
    import inspect
    source = inspect.getsource(app_helpers._show_error)
    auth_branch_start = source.index("🔑 API key issue")
    # The matches(...) call for this branch is the one immediately before it.
    call_start = source.rindex("matches(", 0, auth_branch_start)
    call_text = source[call_start:auth_branch_start]
    for bare_marker in ['"key"', '"api"', '"auth"']:
        assert bare_marker not in call_text, f"found overly broad marker {bare_marker} in auth branch"


def test_show_error_unclassified_error_shows_generic_message_and_logs():
    # Should not raise for a totally generic exception.
    _show_error(ValueError("something totally unexpected happened"), context="test context")


def test_show_error_never_raises_for_various_exception_types():
    for exc in [
        Exception("503 Service Unavailable"),
        TimeoutError("Request timed out after 30s"),
        PermissionError("401 Unauthorized: invalid_api_key"),
        ValueError("unexpected"),
        Exception(""),
    ]:
        _show_error(exc)  # must never raise


# ---------- check_and_consume_rate_limits (consolidated gate) ----------

def _fresh_session_limiter_state():
    st.session_state["ai_limiter"] = RateLimiter(max_calls=15, window_seconds=60)
    st.session_state["session_ai_calls"] = 0


def test_check_and_consume_allows_first_request():
    _fresh_session_limiter_state()
    allowed, msg = check_and_consume_rate_limits()
    assert allowed is True
    assert msg == ""


def test_check_and_consume_increments_session_calls_on_success():
    _fresh_session_limiter_state()
    check_and_consume_rate_limits()
    assert st.session_state["session_ai_calls"] == 1


def test_check_and_consume_blocks_at_session_cap():
    _fresh_session_limiter_state()
    st.session_state["session_ai_calls"] = SESSION_AI_CALL_LIMIT
    allowed, msg = check_and_consume_rate_limits()
    assert allowed is False
    assert "free AI call" in msg


def test_check_and_consume_bypassed_entirely_by_user_key():
    _fresh_session_limiter_state()
    st.session_state["session_ai_calls"] = SESSION_AI_CALL_LIMIT  # would otherwise block
    allowed, msg = check_and_consume_rate_limits(user_key="some-key")
    assert allowed is True
    assert msg == ""
    # BYOK bypasses entirely -- session counter must not even be touched.
    assert st.session_state["session_ai_calls"] == SESSION_AI_CALL_LIMIT


def test_check_and_consume_does_not_waste_session_slot_when_global_limit_blocks():
    """Regression test for B7: previously, the per-session sliding-window
    limiter was consumed (mutated) *before* the global daily-budget check
    ran, so a request that was ultimately blocked by the global limit
    still wasted one of the user's 15-per-60s session slots. Now, both
    limits are peeked (non-mutating) before either is actually consumed.
    """
    _fresh_session_limiter_state()
    limiter = get_global_limiter()
    # Exhaust the global budget so the global check will block.
    for _ in range(limiter.daily_budget):
        limiter.allow()
    assert limiter.remaining() == 0

    allowed, msg = check_and_consume_rate_limits()

    assert allowed is False
    assert "shared daily AI quota" in msg
    # The critical assertion: the session's sliding-window limiter must
    # NOT have been consumed for this blocked request.
    assert st.session_state["ai_limiter"].would_allow() is True
    assert len(st.session_state["ai_limiter"].calls) == 0
    # Nor should the session call counter have incremented.
    assert st.session_state["session_ai_calls"] == 0


def test_check_and_consume_does_not_waste_global_slot_when_session_limit_blocks():
    _fresh_session_limiter_state()
    st.session_state["session_ai_calls"] = SESSION_AI_CALL_LIMIT
    limiter = get_global_limiter()
    remaining_before = limiter.remaining()

    allowed, msg = check_and_consume_rate_limits()

    assert allowed is False
    assert limiter.remaining() == remaining_before  # global budget untouched
