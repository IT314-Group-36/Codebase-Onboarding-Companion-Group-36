"""Per-user rate limiting: a small in-process sliding-window limiter.

Why not slowapi/Redis: the API runs as ONE uvicorn process (jobs run inside it too), so an in-memory limiter is
exact and adds no dependency, no service and no extra cost. If the API is ever scaled to several processes, each
process counts separately (a user could get N times the limit): move the counters to Redis at that point.

A limit is "at most N hits in the last W seconds". A request that is refused is NOT counted, so a user who keeps
retrying is not locked out for longer than the window.
"""
import time
from collections import deque

from fastapi import HTTPException

from app.core.config import get_settings

Rule = tuple[int, float]            # (maximum hits, window in seconds)


class SlidingWindowLimiter:
    def __init__(self, clock=time.monotonic):
        self._clock = clock
        self._hits: dict[tuple, deque[float]] = {}

    def acquire(self, key: str, rules: list[Rule]) -> float | None:
        """Count one hit for `key` against every rule. Returns None when allowed, otherwise the number of seconds
        to wait. Either all rules are updated (allowed) or none is (refused)."""
        now = self._clock()
        wait = 0.0
        slots = []
        for limit, window in rules:
            hits = self._hits.setdefault((key, window), deque())
            while hits and now - hits[0] >= window:
                hits.popleft()
            if len(hits) >= limit:
                wait = max(wait, window - (now - hits[0]))
            slots.append(hits)
        if wait > 0:
            return wait
        for hits in slots:
            hits.append(now)
        if len(self._hits) > 10_000:                 # forget users who have been quiet for a whole window
            self._purge(now)
        return None

    def _purge(self, now: float) -> None:
        for key in [k for k, hits in self._hits.items() if not hits or now - hits[-1] >= k[1]]:
            del self._hits[key]

    def reset(self) -> None:
        self._hits.clear()


limiter = SlidingWindowLimiter()


def _enforce(user_id: int, bucket: str, rules: list[Rule], what: str) -> None:
    if not get_settings().rate_limit_enabled:
        return
    wait = limiter.acquire(f"{bucket}:{user_id}", rules)
    if wait is not None:
        seconds = max(1, int(wait + 0.999))
        raise HTTPException(429, f"Too many {what}. Please wait {seconds} second{'s' if seconds != 1 else ''} and try again.",
                            headers={"Retry-After": str(seconds)})


def enforce_llm(user_id: int) -> None:
    """For requests that call the LLM (and so spend Gemini quota)."""
    s = get_settings()
    _enforce(user_id, "llm", [(s.rate_limit_llm_per_minute, 60), (s.rate_limit_llm_per_hour, 3600)], "AI requests")


def enforce_read(user_id: int) -> None:
    """For requests that search or analyse an indexed repository (they embed the query or load the graphs)."""
    _enforce(user_id, "read", [(get_settings().rate_limit_read_per_minute, 60)], "requests")


def enforce_index(user_id: int) -> None:
    """For requests that start background work: adding, re-indexing and syncing issues."""
    _enforce(user_id, "index", [(get_settings().rate_limit_index_per_hour, 3600)], "indexing requests")


def enforce_refresh(user_id: int) -> None:
    """For /explain?refresh=true, which always makes a new LLM call and overwrites the cache."""
    _enforce(user_id, "refresh", [(get_settings().rate_limit_refresh_per_hour, 3600)], "explanation refreshes")
