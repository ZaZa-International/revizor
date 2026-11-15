from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Select, func, select

from app.domain.enums import DefectStatus, ReviewDecision
from app.infrastructure.database.models.defect import Defect, defect_observations
from app.infrastructure.database.models.review import Review
from app.infrastructure.database.repositories.base import (
    BaseRepository,
    Page,
    apply_sorting,
    paginate,
)


class DefectRepository(BaseRepository[Defect]):
    model = Defect
    entity_name = "Defect"

    async def find_open_by_type(self, asset_id: uuid.UUID, defect_type: str) -> Defect | None:
        stmt = select(Defect).where(
            Defect.asset_id == asset_id,
            Defect.defect_type == defect_type,
            Defect.status.in_(
                [DefectStatus.OPEN, DefectStatus.CONFIRMED, DefectStatus.IN_PROGRESS]
            ),
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def link_observation(self, defect: Defect, observation_id: uuid.UUID) -> None:
        stmt = select(defect_observations).where(
            defect_observations.c.defect_id == defect.id,
            defect_observations.c.observation_id == observation_id,
        )
        if (await self.session.execute(stmt)).first() is None:
            await self.session.execute(
                defect_observations.insert().values(
                    defect_id=defect.id, observation_id=observation_id
                )
            )

    async def observation_count(self, defect_id: uuid.UUID) -> int:
        stmt = (
            select(func.count())
            .select_from(defect_observations)
            .where(defect_observations.c.defect_id == defect_id)
        )
        return int((await self.session.execute(stmt)).scalar_one())

    def filtered_stmt(
        self,
        *,
        asset_id: uuid.UUID | None = None,
        status: DefectStatus | None = None,
        defect_type: str | None = None,
        severity_min: int | None = None,
        severity_max: int | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
    ) -> Select[Any]:
        stmt = select(Defect)
        if asset_id is not None:
            stmt = stmt.where(Defect.asset_id == asset_id)
        if status is not None:
            stmt = stmt.where(Defect.status == status)
        if defect_type is not None:
            stmt = stmt.where(Defect.defect_type == defect_type)
        if severity_min is not None:
            stmt = stmt.where(Defect.severity >= severity_min)
        if severity_max is not None:
            stmt = stmt.where(Defect.severity <= severity_max)
        if date_from is not None:
            stmt = stmt.where(Defect.last_detected_at >= date_from)
        if date_to is not None:
            stmt = stmt.where(Defect.last_detected_at <= date_to)
        return stmt

    async def list_paginated(
        self,
        stmt: Select[Any],
        *,
        page: int,
        page_size: int,
        sort_by: str | None,
        order: str,
    ) -> Page[Defect]:
        stmt = apply_sorting(
            stmt,
            Defect,
            sort_by,
            order,
            {
                "created_at": Defect.created_at,
                "last_detected_at": Defect.last_detected_at,
                "severity": Defect.severity,
                "status": Defect.status,
            },
        )
        return await paginate(self.session, stmt, page=page, page_size=page_size)


class ReviewRepository(BaseRepository[Review]):
    model = Review
    entity_name = "Review"

    async def latest_for_observation(self, observation_id: uuid.UUID) -> Review | None:
        stmt = (
            select(Review)
            .where(Review.observation_id == observation_id)
            .order_by(Review.reviewed_at.desc(), Review.created_at.desc())
            .limit(1)
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def list_for_observation(self, observation_id: uuid.UUID) -> list[Review]:
        stmt = (
            select(Review)
            .where(Review.observation_id == observation_id)
            .order_by(Review.reviewed_at.asc())
        )
        return list((await self.session.execute(stmt)).scalars().all())

    def filtered_stmt(
        self,
        *,
        observation_id: uuid.UUID | None = None,
        defect_id: uuid.UUID | None = None,
        reviewer_id: uuid.UUID | None = None,
        decision: ReviewDecision | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
    ) -> Select[Any]:
        stmt = select(Review)
        if observation_id is not None:
            stmt = stmt.where(Review.observation_id == observation_id)
        if defect_id is not None:
            stmt = stmt.where(Review.defect_id == defect_id)
        if reviewer_id is not None:
            stmt = stmt.where(Review.reviewer_id == reviewer_id)
        if decision is not None:
            stmt = stmt.where(Review.decision == decision)
        if date_from is not None:
            stmt = stmt.where(Review.reviewed_at >= date_from)
        if date_to is not None:
            stmt = stmt.where(Review.reviewed_at <= date_to)
        return stmt

    async def list_paginated(
        self,
        stmt: Select[Any],
        *,
        page: int,
        page_size: int,
        sort_by: str | None,
        order: str,
    ) -> Page[Review]:
        stmt = apply_sorting(
            stmt,
            Review,
            sort_by,
            order,
            {"reviewed_at": Review.reviewed_at, "created_at": Review.created_at},
        )
        return await paginate(self.session, stmt, page=page, page_size=page_size)
