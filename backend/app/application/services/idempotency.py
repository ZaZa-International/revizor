"""Idempotency-Key support for unsafe POST endpoints."""

from __future__ import annotations

import uuid

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.models.idempotency import IdempotencyRecord
from app.infrastructure.database.repositories.misc import IdempotencyRepository


class IdempotencyService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._records = IdempotencyRepository(session)

    async def get_cached(
        self, key: str, user_id: uuid.UUID, endpoint: str
    ) -> IdempotencyRecord | None:
        return await self._records.get(key, user_id, endpoint)

    async def save(
        self,
        *,
        key: str,
        user_id: uuid.UUID,
        endpoint: str,
        status: int,
        body: dict,
        request_hash: str | None = None,
    ) -> None:
        try:
            async with self._session.begin_nested():
                self._records.save(
                    key=key,
                    user_id=user_id,
                    endpoint=endpoint,
                    status=status,
                    body=body,
                    request_hash=request_hash,
                )
                await self._session.flush()
        except IntegrityError:
            pass
