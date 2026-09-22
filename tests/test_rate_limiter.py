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


def test_ratelimiter_would_allow_does_not_mutate():
    rl = RateLimiter(max_calls=1, window_seconds=60)
    assert rl.would_allow() is True
    assert rl.would_allow() is True  # peeking repeatedly doesn't consume
    assert len(rl.calls) == 0
    assert rl.allow() is True
    assert rl.would_allow() is False  # now actually consumed


def test_global_limiter_would_allow_does_not_mutate():
    limiter = GlobalRateLimiter(daily_budget=1)
    assert limiter.would_allow() is True
    assert limiter.would_allow() is True  # peeking repeatedly doesn't consume
    assert limiter.remaining() == 1
    assert limiter.allow() is True
    assert limiter.would_allow() is False


def test_global_limiter_survives_process_restart_when_backed_by_db(tmp_path):
    """Regression test: without db_path, an exhausted GlobalRateLimiter's
    budget silently reset to full on every process restart (a redeploy, a
    crash, a host recycling an idle instance), quietly widening the
    protection this class exists to provide. A second instance pointed at
    the same DB (simulating the process restarting) must pick up where the
    first left off instead of starting over.
    """
    db_path = str(tmp_path / "test_rate_limit.db")
    import persistence
    persistence.init_db(db_path)

    first = GlobalRateLimiter(daily_budget=3, db_path=db_path)
    assert first.allow() is True
    assert first.allow() is True
    assert first.remaining() == 1

    # Simulate a process restart: a fresh instance, same DB file.
    second = GlobalRateLimiter(daily_budget=3, db_path=db_path)
    assert second.remaining() == 1, "restart silently reset the exhausted budget back to full"
    assert second.allow() is True
    assert second.allow() is False


def test_global_limiter_stale_day_in_db_does_not_carry_over(tmp_path):
    """A persisted count from a previous day must not leak into today's
    budget -- only today's row should ever be hydrated."""
    db_path = str(tmp_path / "test_rate_limit.db")
    import persistence
    persistence.init_db(db_path)
    persistence.save_global_rate_limit(db_path, "2000-01-01", 999)

    limiter = GlobalRateLimiter(daily_budget=5, db_path=db_path)
    assert limiter.remaining() == 5


def test_global_limiter_without_db_path_is_unaffected():
    """No db_path -- e.g. persistence unavailable -- must behave exactly
    like before: pure in-memory, no crash from a missing DB file."""
    limiter = GlobalRateLimiter(daily_budget=2)
    assert limiter.allow() is True
    assert limiter.allow() is True
    assert limiter.allow() is False
