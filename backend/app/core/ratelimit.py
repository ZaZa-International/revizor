"""Sliding-window rate limiting backed by Redis.

On Redis outage the limiter falls back to a process-wide shared in-memory
limiter (SEC-15/ARCH-28) so limits still accumulate across per-request
RateLimiter instances. With redis=None each instance keeps its own local
window (used by unit tests).
"""

from __future__ import annotations

import time
import uuid
from collections import defaultdict, deque

import structlog
from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.exceptions import RateLimitError

logger = structlog.get_logger("app.ratelimit")


class RateLimiter:
    def __init__(self, redis: Redis | None = None) -> None:
        self._redis = redis
        self._local: dict[str, deque[float]] = defaultdict(deque)

    async def check(self, key: str, limit: int, window_seconds: int = 60) -> None:
        if self._redis is not None:
            try:
                await self._check_redis(self._redis, key, limit, window_seconds)
                return
            except RedisError:
                logger.warning("ratelimit_redis_unavailable_fallback", key=key)
                await _shared_memory_limiter._check_memory(key, limit, window_seconds)
                return
        await self._check_memory(key, limit, window_seconds)

    async def _check_redis(self, redis: Redis, key: str, limit: int, window_seconds: int) -> None:
        now = time.time()
        redis_key = f"ratelimit:{key}"
        pipe = redis.pipeline()
        pipe.zremrangebyscore(redis_key, 0, now - window_seconds)
        pipe.zadd(redis_key, {f"{now}:{uuid.uuid4()}": now})
        pipe.zcard(redis_key)
        pipe.expire(redis_key, window_seconds + 1)
        results = await pipe.execute()
        count = int(results[2])
        if count > limit:
            raise RateLimitError(retry_after_seconds=window_seconds)

    async def _check_memory(self, key: str, limit: int, window_seconds: int) -> None:
        now = time.time()
        bucket = self._local[key]
        while bucket and bucket[0] <= now - window_seconds:
            bucket.popleft()
        bucket.append(now)
        if len(bucket) > limit:
            raise RateLimitError(retry_after_seconds=window_seconds)


_shared_memory_limiter = RateLimiter()
