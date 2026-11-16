from __future__ import annotations

import uuid

from sqlalchemy import select

from app.infrastructure.database.models.history import AssetConditionHistory
from app.infrastructure.database.models.idempotency import IdempotencyRecord
from app.infrastructure.database.models.training import TrainingExample
from app.infrastructure.database.repositories.base import BaseRepository, Page, paginate


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

    async def paginated(
        self, asset_id: uuid.UUID, *, page: int, page_size: int
    ) -> Page[AssetConditionHistory]:
        stmt = (
            select(AssetConditionHistory)
            .where(AssetConditionHistory.asset_id == asset_id)
            .order_by(
                AssetConditionHistory.detected_at.desc(),
                AssetConditionHistory.id.desc(),
            )
        )
        return await paginate(self.session, stmt, page=page, page_size=page_size)


class TrainingExampleRepository(BaseRepository[TrainingExample]):
    model = TrainingExample
    entity_name = "TrainingExample"

    async def get_by_observation(self, observation_id: uuid.UUID) -> TrainingExample | None:
        stmt = select(TrainingExample).where(TrainingExample.observation_id == observation_id)
        return (await self.session.execute(stmt)).scalar_one_or_none()


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
        self,
        *,
        key: str,
        user_id: uuid.UUID,
        endpoint: str,
        status: int,
        body: dict,
        request_hash: str | None = None,
    ) -> IdempotencyRecord:
        return self.add(
            IdempotencyRecord(
                key=key,
                user_id=user_id,
                endpoint=endpoint,
                request_hash=request_hash,
                response_status=status,
                response_body=body,
            )
        )
