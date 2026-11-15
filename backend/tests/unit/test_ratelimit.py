"""RateLimiter in-memory fallback: sliding window limit and expiry."""

from __future__ import annotations

import pytest
from app.core import ratelimit as ratelimit_module
from app.core.exceptions import RateLimitError
from app.core.ratelimit import RateLimiter

pytestmark = pytest.mark.unit


async def test_in_memory_limit_raises_on_excess():
    limiter = RateLimiter(None)
    for _ in range(3):
        await limiter.check("key", 3)
    with pytest.raises(RateLimitError) as excinfo:
        await limiter.check("key", 3)
    assert excinfo.value.retry_after_seconds == 60
    assert excinfo.value.status_code == 429
    assert excinfo.value.code == "rate_limited"


async def test_keys_are_independent():
    limiter = RateLimiter(None)
    for _ in range(3):
        await limiter.check("a", 3)
    await limiter.check("b", 3)
    with pytest.raises(RateLimitError):
        await limiter.check("a", 3)


async def test_window_expiry_allows_new_requests(monkeypatch):
    clock = {"now": 1_000.0}
    monkeypatch.setattr(ratelimit_module.time, "time", lambda: clock["now"])
    limiter = RateLimiter(None)
    for _ in range(3):
        await limiter.check("key", 3)
    with pytest.raises(RateLimitError):
        await limiter.check("key", 3)
    clock["now"] += 61.0
    await limiter.check("key", 3)
    await limiter.check("key", 3)
    await limiter.check("key", 3)
    with pytest.raises(RateLimitError):
        await limiter.check("key", 3)
