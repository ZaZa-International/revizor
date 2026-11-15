from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Header, Query
from fastapi.responses import JSONResponse

from app.api.v1.idempotency import idempotent_post
from app.application.services.history import AssetHistoryService
from app.application.services.reviews import ReviewService
from app.application.services.risk import RiskScoringService
from app.dependencies import CurrentUser, OperatorOrAdmin, SessionDep, SettingsDep
from app.domain.enums import ReviewDecision
from app.domain.reviews.logic import ReviewCorrection
from app.infrastructure.database.repositories.defects import ReviewRepository
from app.schemas.assets import ReviewCreateRequest, ReviewResponse
from app.schemas.common import PageResponse

router = APIRouter(prefix="/reviews", tags=["reviews"])


@router.post("", summary="Submit operator review (append-only)")
async def create_review(
    body: ReviewCreateRequest,
    session: SessionDep,
    settings: SettingsDep,
    user: OperatorOrAdmin,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> JSONResponse:
    async def handler() -> tuple[int, dict]:
        service = ReviewService(session, RiskScoringService(settings), AssetHistoryService(session))
        review = await service.create_review(
            observation_id=body.observation_id,
            defect_id=body.defect_id,
            reviewer_id=user.id,
            decision=body.decision,
            correction=ReviewCorrection(
                corrected_asset_type=body.corrected_asset_type,
                corrected_condition=body.corrected_condition,
                corrected_defect_type=body.corrected_defect_type,
                corrected_severity=body.corrected_severity,
            ),
            comment=body.comment,
            reviewed_at=body.reviewed_at,
        )
        return 201, ReviewResponse.model_validate(review).model_dump(mode="json")

    return await idempotent_post(
        session, user_id=user.id, endpoint="POST /reviews", key=idempotency_key, handler=handler
    )


@router.get("", response_model=PageResponse[ReviewResponse], summary="List reviews")
async def list_reviews(
    session: SessionDep,
    user: CurrentUser,
    observation_id: uuid.UUID | None = None,
    defect_id: uuid.UUID | None = None,
    reviewer_id: uuid.UUID | None = None,
    decision: ReviewDecision | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    sort_by: str | None = None,
    order: Literal["asc", "desc"] = "desc",
) -> dict:
    repo = ReviewRepository(session)
    stmt = repo.filtered_stmt(
        observation_id=observation_id,
        defect_id=defect_id,
        reviewer_id=reviewer_id,
        decision=decision,
        date_from=date_from,
        date_to=date_to,
    )
    result = await repo.list_paginated(
        stmt, page=page, page_size=page_size, sort_by=sort_by, order=order
    )
    return {
        "items": [ReviewResponse.model_validate(r).model_dump(mode="json") for r in result.items],
        "total": result.total,
        "page": result.page,
        "page_size": result.page_size,
        "pages": result.pages,
    }


@router.get("/{review_id}", response_model=ReviewResponse, summary="Get review")
async def get_review(
    review_id: uuid.UUID, session: SessionDep, user: CurrentUser
) -> ReviewResponse:
    review = await ReviewRepository(session).get_or_raise(review_id)
    return ReviewResponse.model_validate(review)
