import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from rate_limiter import RateLimiter, GlobalRateLimiter


def test_ratelimiter_allows_up_to_max_calls():
    rl = RateLimiter(max_calls=3, window_seconds=60)
    assert rl.allow() is True
    assert rl.allow() is True
    assert rl.allow() is True
    assert rl.allow() is False


def test_ratelimiter_window_expiry_frees_capacity():
    rl = RateLimiter(max_calls=1, window_seconds=0.05)
    assert rl.allow() is True
    assert rl.allow() is False
    time.sleep(0.06)
    assert rl.allow() is True


def test_global_limiter_allows_up_to_daily_budget():
    limiter = GlobalRateLimiter(daily_budget=2)
    assert limiter.allow() is True
    assert limiter.allow() is True
    assert limiter.allow() is False


def test_global_limiter_remaining_reflects_usage():
    limiter = GlobalRateLimiter(daily_budget=5)
    limiter.allow()
    limiter.allow()
    assert limiter.remaining() == 3


def test_global_limiter_is_shared_state_not_per_call():
    """The whole point of GlobalRateLimiter: the same instance's budget is
    shared across every caller, unlike per-session state."""
    limiter = GlobalRateLimiter(daily_budget=1)
    caller_a_allowed = limiter.allow()
    caller_b_allowed = limiter.allow()
    assert caller_a_allowed is True
    assert caller_b_allowed is False
