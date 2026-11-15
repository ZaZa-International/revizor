from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select

from app.domain.enums import TrainingExampleStatus
from app.infrastructure.database.models.history import AssetConditionHistory
from app.infrastructure.database.models.idempotency import IdempotencyRecord
from app.infrastructure.database.models.training import TrainingExample
from app.infrastructure.database.repositories.base import BaseRepository


class HistoryRepository(BaseRepository[AssetConditionHistory]):
    model = AssetConditionHistory
    entity_name = "AssetConditionHistory"

    async def list_for_asset(self, asset_id: uuid.UUID) -> list[AssetConditionHistory]:
        stmt = (
            select(AssetConditionHistory)
            .where(AssetConditionHistory.asset_id == asset_id)
            .order_by(AssetConditionHistory.detected_at.asc())
        )
        return list((await self.session.execute(stmt)).scalars().all())


class TrainingExampleRepository(BaseRepository[TrainingExample]):
    model = TrainingExample
    entity_name = "TrainingExample"

    async def get_by_observation(self, observation_id: uuid.UUID) -> TrainingExample | None:
        stmt = select(TrainingExample).where(TrainingExample.observation_id == observation_id)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def list_pending(self, limit: int = 1000) -> list[TrainingExample]:
        stmt = (
            select(TrainingExample)
            .where(TrainingExample.status == TrainingExampleStatus.PENDING)
            .order_by(TrainingExample.created_at.asc())
            .limit(limit)
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def mark_exported(self, examples: list[TrainingExample]) -> None:
        now = datetime.now(UTC)
        for example in examples:
            example.status = TrainingExampleStatus.EXPORTED
            example.exported_at = now


class IdempotencyRepository(BaseRepository[IdempotencyRecord]):
    model = IdempotencyRecord
    entity_name = "IdempotencyRecord"

    async def get(self, key: str, user_id: uuid.UUID, endpoint: str) -> IdempotencyRecord | None:  # type: ignore[override]
        stmt = select(IdempotencyRecord).where(
            IdempotencyRecord.key == key,
            IdempotencyRecord.user_id == user_id,
            IdempotencyRecord.endpoint == endpoint,
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    def save(
        self, *, key: str, user_id: uuid.UUID, endpoint: str, status: int, body: dict
    ) -> IdempotencyRecord:
        return self.add(
            IdempotencyRecord(
                key=key,
                user_id=user_id,
                endpoint=endpoint,
                response_status=status,
                response_body=body,
            )
        )
