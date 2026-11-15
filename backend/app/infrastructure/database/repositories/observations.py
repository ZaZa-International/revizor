from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Select, func, select

from app.domain.enums import DeduplicationResult, ObservationReviewStatus
from app.domain.geospatial.models import BoundingBox
from app.infrastructure.database.models.observation import Observation
from app.infrastructure.database.repositories.assets import bbox_element
from app.infrastructure.database.repositories.base import (
    BaseRepository,
    Page,
    apply_sorting,
    paginate,
)


class ObservationRepository(BaseRepository[Observation]):
    model = Observation
    entity_name = "Observation"

    async def exists_by_job_detection(self, job_id: uuid.UUID, detection_id: uuid.UUID) -> bool:
        stmt = select(func.count(Observation.id)).where(
            Observation.processing_job_id == job_id,
            Observation.detection_id == detection_id,
        )
        return int((await self.session.execute(stmt)).scalar_one()) > 0

    async def latest_for_asset(self, asset_id: uuid.UUID) -> Observation | None:
        stmt = (
            select(Observation)
            .where(Observation.asset_id == asset_id)
            .order_by(Observation.observed_at.desc())
            .limit(1)
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def count_for_asset(self, asset_id: uuid.UUID) -> int:
        stmt = select(func.count(Observation.id)).where(Observation.asset_id == asset_id)
        return int((await self.session.execute(stmt)).scalar_one())

    def filtered_stmt(
        self,
        *,
        asset_id: uuid.UUID | None = None,
        job_id: uuid.UUID | None = None,
        object_type: str | None = None,
        review_status: ObservationReviewStatus | None = None,
        dedup_result: DeduplicationResult | None = None,
        bbox: BoundingBox | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
    ) -> Select[Any]:
        stmt = select(Observation)
        if asset_id is not None:
            stmt = stmt.where(Observation.asset_id == asset_id)
        if job_id is not None:
            stmt = stmt.where(Observation.processing_job_id == job_id)
        if object_type is not None:
            stmt = stmt.where(Observation.object_type == object_type)
        if review_status is not None:
            stmt = stmt.where(Observation.review_status == review_status)
        if dedup_result is not None:
            stmt = stmt.where(Observation.dedup_result == dedup_result)
        if bbox is not None:
            stmt = stmt.where(
                Observation.location.is_not(None),
                func.ST_Intersects(Observation.location, bbox_element(bbox)),
            )
        if date_from is not None:
            stmt = stmt.where(Observation.observed_at >= date_from)
        if date_to is not None:
            stmt = stmt.where(Observation.observed_at <= date_to)
        return stmt

    async def list_paginated(
        self,
        stmt: Select[Any],
        *,
        page: int,
        page_size: int,
        sort_by: str | None,
        order: str,
    ) -> Page[Observation]:
        stmt = apply_sorting(
            stmt,
            Observation,
            sort_by,
            order,
            {
                "observed_at": Observation.observed_at,
                "created_at": Observation.created_at,
                "detector_confidence": Observation.detector_confidence,
            },
        )
        return await paginate(self.session, stmt, page=page, page_size=page_size)
