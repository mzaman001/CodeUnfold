import time
import threading


class RateLimiter:
    """Per-session sliding-window limiter, held in `st.session_state`.

    Streamlit session state is scoped to a single browser websocket
    connection. That makes this a good UX nudge (stops one open tab from
    hammering the AI endpoint in a tight loop) but NOT abuse protection:
    a tab refresh, a new private window, or a scripted client cycling
    sessions each gets its own fresh instance of this limiter. Real,
    shared-quota protection lives in `GlobalRateLimiter` below.
    """

    def __init__(self, max_calls, window_seconds):
        self.max_calls = max_calls
        self.window = window_seconds
        self.calls = []

    def allow(self) -> bool:
        now = time.time()
        self.calls = [t for t in self.calls if now - t < self.window]
        if len(self.calls) >= self.max_calls:
            return False
        self.calls.append(now)
        return True

    def would_allow(self) -> bool:
        """Non-mutating peek: would the next call() succeed right now?

        Exists so multiple rate limiters can be checked in sequence
        before any of them are actually consumed -- without this, a
        request that passes this limiter but then gets blocked by a
        *different* limiter checked afterward would still have consumed
        one of this limiter's slots for a request that never went
        through.
        """
        now = time.time()
        current_calls = [t for t in self.calls if now - t < self.window]
        return len(current_calls) < self.max_calls


class GlobalRateLimiter:
    """Process-wide daily token bucket shared across every visitor session.

    Intended to be constructed exactly once per running process via
    `st.cache_resource` (see `get_global_limiter()` in app_helpers.py).
    Because `st.cache_resource` objects are shared across *all* sessions on
    that process — unlike `st.session_state`, which is per-browser-session —
    this survives tab refreshes, incognito windows, and new sessions, and
    actually protects the shared Groq/Gemini API keys from being drained
    by ordinary traffic growth rather than only stopping one tab from
    looping.

    Optionally backed by `persistence.py`'s SQLite DB (pass `db_path`):
    without this, the count lived only in the `st.cache_resource` singleton,
    so a process restart (redeploy, crash, a host recycling an idle
    instance) silently reset an exhausted daily budget back to full. With
    `db_path` set, the count is hydrated on construction and persisted
    after every mutating call, so a restart resumes today's count instead
    of quietly re-granting a full quota. Persistence is best-effort: if the
    write fails (read-only filesystem, locked file), this degrades to the
    old in-memory-only behavior for that process rather than raising.

    Caveat, stated plainly: this still only guards a single process/host's
    filesystem. If the app is ever scaled to multiple instances that don't
    share that file (e.g. separate ephemeral containers behind a load
    balancer), each instance gets its own independent budget and the *true*
    aggregate ceiling becomes (budget * instance_count). Closing that gap
    needs a real shared store (e.g. a free-tier Postgres row), not a local
    SQLite file — see the audit's roadmap item 9 for that upgrade path. For
    a single Streamlit Community Cloud instance (the common case for a
    project like this), this closes the redeploy-reset gap for free.
    """

    def __init__(self, daily_budget: int, db_path: str = None):
        self.daily_budget = daily_budget
        self.db_path = db_path
        self._lock = threading.Lock()
        self._count = 0
        self._day = time.strftime("%Y-%m-%d", time.gmtime())
        if self.db_path:
            self._hydrate()

    def _hydrate(self):
        """Loads today's count from the DB, if a matching row exists.
        A stale (prior-day) row is left alone -- _roll_day_if_needed
        naturally starts a fresh day at 0 without needing to touch it.
        """
        import persistence
        saved = persistence.load_global_rate_limit(self.db_path)
        if saved and saved[0] == self._day:
            self._count = saved[1]

    def _persist(self):
        if not self.db_path:
            return
        import persistence
        persistence.save_global_rate_limit(self.db_path, self._day, self._count)

    def _roll_day_if_needed(self):
        today = time.strftime("%Y-%m-%d", time.gmtime())
        if today != self._day:
            self._day = today
            self._count = 0

    def allow(self) -> bool:
        with self._lock:
            self._roll_day_if_needed()
            if self._count >= self.daily_budget:
                return False
            self._count += 1
            self._persist()
            return True

    def remaining(self) -> int:
        with self._lock:
            self._roll_day_if_needed()
            return max(0, self.daily_budget - self._count)

    def would_allow(self) -> bool:
        """Non-mutating peek -- see RateLimiter.would_allow() for why this exists."""
        return self.remaining() > 0
