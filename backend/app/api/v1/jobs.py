from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Header, Query
from fastapi.responses import JSONResponse

from app.api.v1.idempotency import idempotent_post
from app.application.services.jobs import JobService
from app.dependencies import CurrentUser, OperatorOrAdmin, QueueDep, SessionDep
from app.domain.enums import JobStatus
from app.infrastructure.database.repositories.jobs import JobFrameRepository, JobRepository
from app.schemas.common import PageResponse
from app.schemas.uploads import JobCreateRequest, JobFrameResponse, JobResponse

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.post("", summary="Create processing job for an upload")
async def create_job(
    body: JobCreateRequest,
    session: SessionDep,
    queue: QueueDep,
    user: OperatorOrAdmin,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> JSONResponse:
    async def handler() -> tuple[int, dict]:
        service = JobService(session, queue)
        job, created = await service.create_job(
            upload_id=body.upload_id,
            route_id=body.route_id,
            options=body.options,
            idempotency_key=idempotency_key,
            actor_id=user.id,
        )
        return (201 if created else 200), JobResponse.model_validate(job).model_dump(mode="json")

    return await idempotent_post(
        session, user_id=user.id, endpoint="POST /jobs", key=idempotency_key, handler=handler
    )


@router.get("", response_model=PageResponse[JobResponse], summary="List processing jobs")
async def list_jobs(
    session: SessionDep,
    user: CurrentUser,
    status: JobStatus | None = None,
    upload_id: uuid.UUID | None = None,
    route_id: uuid.UUID | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    sort_by: str | None = None,
    order: Literal["asc", "desc"] = "desc",
) -> dict:
    repo = JobRepository(session)
    stmt = repo.filtered_stmt(
        status=status,
        upload_id=upload_id,
        route_id=route_id,
        date_from=date_from,
        date_to=date_to,
    )
    result = await repo.list_paginated(
        stmt, page=page, page_size=page_size, sort_by=sort_by, order=order
    )
    return {
        "items": [JobResponse.model_validate(job).model_dump(mode="json") for job in result.items],
        "total": result.total,
        "page": result.page,
        "page_size": result.page_size,
        "pages": result.pages,
    }


@router.get("/{job_id}", response_model=JobResponse, summary="Get job status and progress")
async def get_job(job_id: uuid.UUID, session: SessionDep, user: CurrentUser) -> JobResponse:
    job = await JobRepository(session).get_or_raise(job_id)
    return JobResponse.model_validate(job)


@router.get("/{job_id}/frames", response_model=list[JobFrameResponse], summary="Per-frame results")
async def get_job_frames(
    job_id: uuid.UUID, session: SessionDep, user: CurrentUser
) -> list[JobFrameResponse]:
    await JobRepository(session).get_or_raise(job_id)
    frames = await JobFrameRepository(session).list_for_job(job_id)
    return [JobFrameResponse.model_validate(frame) for frame in frames]


@router.post("/{job_id}/retry", response_model=JobResponse, summary="Retry failed/partial job")
async def retry_job(
    job_id: uuid.UUID, session: SessionDep, queue: QueueDep, user: OperatorOrAdmin
) -> JobResponse:
    job = await JobService(session, queue).retry_job(job_id, user.id)
    return JobResponse.model_validate(job)


@router.post(
    "/{job_id}/cancel", response_model=JobResponse, summary="Cancel pending/queued/processing job"
)
async def cancel_job(
    job_id: uuid.UUID, session: SessionDep, queue: QueueDep, user: OperatorOrAdmin
) -> JobResponse:
    job = await JobService(session, queue).cancel_job(job_id, user.id)
    return JobResponse.model_validate(job)
