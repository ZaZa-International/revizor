from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Select, select

from app.domain.enums import FrameStatus, JobStatus
from app.infrastructure.database.models.job import JobFrame, ProcessingJob
from app.infrastructure.database.repositories.base import (
    BaseRepository,
    Page,
    apply_sorting,
    paginate,
)


class JobRepository(BaseRepository[ProcessingJob]):
    model = ProcessingJob
    entity_name = "ProcessingJob"

    async def get_by_idempotency_key(self, key: str) -> ProcessingJob | None:
        stmt = select(ProcessingJob).where(ProcessingJob.idempotency_key == key)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    def filtered_stmt(
        self,
        *,
        status: JobStatus | None = None,
        upload_id: uuid.UUID | None = None,
        route_id: uuid.UUID | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
    ) -> Select[Any]:
        stmt = select(ProcessingJob)
        if status is not None:
            stmt = stmt.where(ProcessingJob.status == status)
        if upload_id is not None:
            stmt = stmt.where(ProcessingJob.upload_id == upload_id)
        if route_id is not None:
            stmt = stmt.where(ProcessingJob.route_id == route_id)
        if date_from is not None:
            stmt = stmt.where(ProcessingJob.created_at >= date_from)
        if date_to is not None:
            stmt = stmt.where(ProcessingJob.created_at <= date_to)
        return stmt

    async def list_paginated(
        self,
        stmt: Select[Any],
        *,
        page: int,
        page_size: int,
        sort_by: str | None,
        order: str,
    ) -> Page[ProcessingJob]:
        stmt = apply_sorting(
            stmt,
            ProcessingJob,
            sort_by,
            order,
            {
                "created_at": ProcessingJob.created_at,
                "status": ProcessingJob.status,
                "started_at": ProcessingJob.started_at,
                "finished_at": ProcessingJob.finished_at,
            },
        )
        return await paginate(self.session, stmt, page=page, page_size=page_size)


class JobFrameRepository(BaseRepository[JobFrame]):
    model = JobFrame
    entity_name = "JobFrame"

    async def get_by_index(self, job_id: uuid.UUID, frame_index: int) -> JobFrame | None:
        stmt = select(JobFrame).where(
            JobFrame.job_id == job_id, JobFrame.frame_index == frame_index
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def list_for_job(self, job_id: uuid.UUID) -> list[JobFrame]:
        stmt = (
            select(JobFrame).where(JobFrame.job_id == job_id).order_by(JobFrame.frame_index.asc())
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def paginated(
        self,
        job_id: uuid.UUID,
        *,
        page: int,
        page_size: int,
        status: FrameStatus | None = None,
    ) -> Page[JobFrame]:
        stmt = select(JobFrame).where(JobFrame.job_id == job_id)
        if status is not None:
            stmt = stmt.where(JobFrame.status == status)
        stmt = stmt.order_by(JobFrame.frame_index.asc())
        return await paginate(self.session, stmt, page=page, page_size=page_size)

    async def count_by_status(self, job_id: uuid.UUID, status: FrameStatus) -> int:
        from sqlalchemy import func

        stmt = select(func.count(JobFrame.id)).where(
            JobFrame.job_id == job_id, JobFrame.status == status
        )
        return int((await self.session.execute(stmt)).scalar_one())
