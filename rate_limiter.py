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


class GlobalRateLimiter:
    """Process-wide daily token bucket shared across every visitor session.

    Intended to be constructed exactly once per running process via
    `st.cache_resource` (see `get_global_limiter()` in main.py). Because
    `st.cache_resource` objects are shared across *all* sessions on that
    process — unlike `st.session_state`, which is per-browser-session —
    this survives tab refreshes, incognito windows, and new sessions, and
    actually protects the shared Groq/Gemini API keys from being drained
    by ordinary traffic growth rather than only stopping one tab from
    looping.

    Caveat, stated plainly: this only guards a single process/instance.
    If the app is ever scaled to multiple instances behind a load
    balancer, each instance gets its own independent budget and the
    *true* aggregate ceiling becomes (budget * instance_count). Closing
    that gap needs a durable, cross-instance store (e.g. a free-tier
    Postgres row) — see the audit's roadmap item 9 for that upgrade path.
    For a single Streamlit Community Cloud instance (the common case for
    a project like this), this closes the real gap for free.
    """

    def __init__(self, daily_budget: int):
        self.daily_budget = daily_budget
        self._lock = threading.Lock()
        self._count = 0
        self._day = time.strftime("%Y-%m-%d", time.gmtime())

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
            return True

    def remaining(self) -> int:
        with self._lock:
            self._roll_day_if_needed()
            return max(0, self.daily_budget - self._count)
