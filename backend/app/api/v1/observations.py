from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Query

from app.api.v1.serializers import observation_response
from app.dependencies import CurrentUser, SessionDep, StorageDep, parse_bbox
from app.domain.enums import DeduplicationResult, ObservationReviewStatus
from app.infrastructure.database.repositories.observations import ObservationRepository
from app.schemas.assets import ObservationResponse
from app.schemas.common import PageResponse

router = APIRouter(prefix="/observations", tags=["observations"])


@router.get("", response_model=PageResponse[ObservationResponse], summary="List observations")
async def list_observations(
    session: SessionDep,
    storage: StorageDep,
    user: CurrentUser,
    asset_id: uuid.UUID | None = None,
    job_id: uuid.UUID | None = None,
    object_type: str | None = None,
    review_status: ObservationReviewStatus | None = None,
    dedup_result: DeduplicationResult | None = None,
    bbox: str | None = Query(None, description="min_lon,min_lat,max_lon,max_lat"),
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    sort_by: str | None = None,
    order: Literal["asc", "desc"] = "desc",
) -> dict:
    repo = ObservationRepository(session)
    stmt = repo.filtered_stmt(
        asset_id=asset_id,
        job_id=job_id,
        object_type=object_type,
        review_status=review_status,
        dedup_result=dedup_result,
        bbox=parse_bbox(bbox),
        date_from=date_from,
        date_to=date_to,
    )
    result = await repo.list_paginated(
        stmt, page=page, page_size=page_size, sort_by=sort_by, order=order
    )
    items = [
        (await observation_response(obs, session, storage)).model_dump(mode="json")
        for obs in result.items
    ]
    return {
        "items": items,
        "total": result.total,
        "page": result.page,
        "page_size": result.page_size,
        "pages": result.pages,
    }


@router.get("/{observation_id}", response_model=ObservationResponse, summary="Get observation")
async def get_observation(
    observation_id: uuid.UUID, session: SessionDep, storage: StorageDep, user: CurrentUser
) -> ObservationResponse:
    observation = await ObservationRepository(session).get_or_raise(observation_id)
    return await observation_response(observation, session, storage)
