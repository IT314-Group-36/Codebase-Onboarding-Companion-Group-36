"""The sliding-window limiter (no database needed)."""
import pytest
from fastapi import HTTPException

from app.core import ratelimit
from app.core.config import get_settings
from app.core.ratelimit import SlidingWindowLimiter


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def test_allows_up_to_the_limit_then_says_how_long_to_wait():
    clock = Clock()
    lim = SlidingWindowLimiter(clock)
    for _ in range(3):
        assert lim.acquire("u1", [(3, 60)]) is None
        clock.now += 1
    wait = lim.acquire("u1", [(3, 60)])
    assert wait == pytest.approx(57)             # the oldest hit (3 s ago) leaves the window in 57 s


def test_window_slides_and_refused_hits_are_not_counted():
    clock = Clock()
    lim = SlidingWindowLimiter(clock)
    assert lim.acquire("u1", [(1, 10)]) is None
    for _ in range(5):                           # retrying while blocked must not extend the block
        clock.now += 1
        assert lim.acquire("u1", [(1, 10)]) is not None
    clock.now += 5
    assert lim.acquire("u1", [(1, 10)]) is None


def test_keys_are_independent():
    lim = SlidingWindowLimiter(Clock())
    assert lim.acquire("llm:1", [(1, 60)]) is None
    assert lim.acquire("llm:1", [(1, 60)]) is not None
    assert lim.acquire("llm:2", [(1, 60)]) is None
    assert lim.acquire("read:1", [(1, 60)]) is None


def test_a_refused_request_does_not_use_up_the_other_rules():
    clock = Clock()
    lim = SlidingWindowLimiter(clock)
    rules = [(2, 60), (3, 3600)]
    assert lim.acquire("u", rules) is None and lim.acquire("u", rules) is None
    assert lim.acquire("u", rules) is not None          # minute rule refuses, so the hour counter must stay at 2
    clock.now += 61
    assert lim.acquire("u", rules) is None              # hour counter: 3rd hit
    clock.now += 61
    assert lim.acquire("u", rules) is not None          # hour rule now refuses


def test_quiet_keys_are_purged():
    clock = Clock()
    lim = SlidingWindowLimiter(clock)
    for i in range(10_001):
        lim.acquire(f"u{i}", [(1, 10)])
    clock.now += 11
    lim.acquire("fresh", [(1, 10)])
    assert len(lim._hits) < 10


def test_enforce_raises_429_with_retry_after(monkeypatch):
    ratelimit.limiter.reset()
    monkeypatch.setattr(get_settings(), "rate_limit_read_per_minute", 2)
    ratelimit.enforce_read(7)
    ratelimit.enforce_read(7)
    with pytest.raises(HTTPException) as e:
        ratelimit.enforce_read(7)
    assert e.value.status_code == 429 and int(e.value.headers["Retry-After"]) >= 1
    ratelimit.enforce_read(8)                            # another user is unaffected
    ratelimit.limiter.reset()


def test_can_be_switched_off(monkeypatch):
    ratelimit.limiter.reset()
    monkeypatch.setattr(get_settings(), "rate_limit_enabled", False)
    monkeypatch.setattr(get_settings(), "rate_limit_refresh_per_hour", 1)
    for _ in range(5):
        ratelimit.enforce_refresh(1)
