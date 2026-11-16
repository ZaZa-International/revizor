"""Idempotency-Key replay helper for unsafe POST endpoints.

Replay with a different request fingerprint raises IdempotencyConflictError
(409 idempotency_conflict); identical replays return the cached body/status.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable

from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.services.idempotency import IdempotencyService
from app.core.exceptions import IdempotencyConflictError


async def idempotent_post(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    endpoint: str,
    key: str | None,
    handler: Callable[[], Awaitable[tuple[int, dict]]],
    request_hash: str | None = None,
    result_hash: Callable[[dict], str | None] | None = None,
) -> JSONResponse:
    service = IdempotencyService(session)
    if key:
        await session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:k, 0))"),
            {"k": f"idem:{user_id}:{endpoint}:{key}"},
        )
        cached = await service.get_cached(key, user_id, endpoint)
        if cached is not None:
            if cached.request_hash and request_hash and cached.request_hash != request_hash:
                raise IdempotencyConflictError(
                    "Idempotency-Key was already used with a different request payload"
                )
            return JSONResponse(status_code=cached.response_status, content=cached.response_body)
    status, body = await handler()
    if key:
        fingerprint = request_hash
        if fingerprint is None and result_hash is not None:
            fingerprint = result_hash(body)
        await service.save(
            key=key,
            user_id=user_id,
            endpoint=endpoint,
            status=status,
            body=body,
            request_hash=fingerprint,
        )
    return JSONResponse(status_code=status, content=body)
