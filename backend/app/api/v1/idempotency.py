"""Idempotency-Key replay helper for unsafe POST endpoints."""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable

from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.services.idempotency import IdempotencyService


async def idempotent_post(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    endpoint: str,
    key: str | None,
    handler: Callable[[], Awaitable[tuple[int, dict]]],
) -> JSONResponse:
    service = IdempotencyService(session)
    if key:
        cached = await service.get_cached(key, user_id, endpoint)
        if cached is not None:
            return JSONResponse(status_code=cached.response_status, content=cached.response_body)
    status, body = await handler()
    if key:
        await service.save(key=key, user_id=user_id, endpoint=endpoint, status=status, body=body)
    return JSONResponse(status_code=status, content=body)
