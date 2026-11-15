"""Sliding-window rate limiting backed by Redis (in-memory fallback for tests)."""

from __future__ import annotations

import time
from collections import defaultdict, deque

from redis.asyncio import Redis

from app.core.exceptions import RateLimitError


class RateLimiter:
    def __init__(self, redis: Redis | None = None) -> None:
        self._redis = redis
        self._local: dict[str, deque[float]] = defaultdict(deque)

    async def check(self, key: str, limit: int, window_seconds: int = 60) -> None:
        now = time.time()
        if self._redis is not None:
            redis_key = f"ratelimit:{key}"
            pipe = self._redis.pipeline()
            pipe.zremrangebyscore(redis_key, 0, now - window_seconds)
            pipe.zadd(redis_key, {str(now): now})
            pipe.zcard(redis_key)
            pipe.expire(redis_key, window_seconds + 1)
            results = await pipe.execute()
            count = int(results[2])
            if count > limit:
                raise RateLimitError(retry_after_seconds=window_seconds)
            return
        bucket = self._local[key]
        while bucket and bucket[0] <= now - window_seconds:
            bucket.popleft()
        bucket.append(now)
        if len(bucket) > limit:
            raise RateLimitError(retry_after_seconds=window_seconds)
