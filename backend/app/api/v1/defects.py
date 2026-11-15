from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Query

from app.core.exceptions import ValidationAppError
from app.dependencies import CurrentUser, OperatorOrAdmin, SessionDep
from app.domain.enums import AuditAction, DefectStatus
from app.infrastructure.database.repositories.defects import DefectRepository
from app.infrastructure.database.repositories.users import AuditRepository
from app.schemas.assets import DefectPatchRequest, DefectResponse
from app.schemas.common import PageResponse

router = APIRouter(prefix="/defects", tags=["defects"])


@router.get("", response_model=PageResponse[DefectResponse], summary="List defects")
async def list_defects(
    session: SessionDep,
    user: CurrentUser,
    asset_id: uuid.UUID | None = None,
    status: DefectStatus | None = None,
    defect_type: str | None = None,
    severity_min: int | None = Query(None, ge=1, le=5),
    severity_max: int | None = Query(None, ge=1, le=5),
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    sort_by: str | None = None,
    order: Literal["asc", "desc"] = "desc",
) -> dict:
    repo = DefectRepository(session)
    stmt = repo.filtered_stmt(
        asset_id=asset_id,
        status=status,
        defect_type=defect_type,
        severity_min=severity_min,
        severity_max=severity_max,
        date_from=date_from,
        date_to=date_to,
    )
    result = await repo.list_paginated(
        stmt, page=page, page_size=page_size, sort_by=sort_by, order=order
    )
    items = []
    for defect in result.items:
        response = DefectResponse.model_validate(defect)
        response.observation_count = await repo.observation_count(defect.id)
        items.append(response.model_dump(mode="json"))
    return {
        "items": items,
        "total": result.total,
        "page": result.page,
        "page_size": result.page_size,
        "pages": result.pages,
    }


@router.get("/{defect_id}", response_model=DefectResponse, summary="Get defect")
async def get_defect(
    defect_id: uuid.UUID, session: SessionDep, user: CurrentUser
) -> DefectResponse:
    repo = DefectRepository(session)
    defect = await repo.get_or_raise(defect_id)
    response = DefectResponse.model_validate(defect)
    response.observation_count = await repo.observation_count(defect.id)
    return response


@router.patch(
    "/{defect_id}", response_model=DefectResponse, summary="Update defect status/severity"
)
async def patch_defect(
    defect_id: uuid.UUID,
    body: DefectPatchRequest,
    session: SessionDep,
    user: OperatorOrAdmin,
) -> DefectResponse:
    repo = DefectRepository(session)
    defect = await repo.get_or_raise(defect_id)
    before = {"status": defect.status.value, "severity": defect.severity}
    if body.status is not None:
        if body.status == DefectStatus.RESOLVED and defect.status == DefectStatus.REJECTED:
            raise ValidationAppError("Rejected defect cannot be resolved; review it first")
        defect.status = body.status
        defect.resolved_at = datetime.now(UTC) if body.status == DefectStatus.RESOLVED else None
    if body.severity is not None:
        defect.severity = body.severity
    if body.description is not None:
        defect.description = body.description
    AuditRepository(session).record(
        actor_id=user.id,
        action=AuditAction.UPDATE.value,
        entity_type="defect",
        entity_id=defect.id,
        before_state=before,
        after_state={"status": defect.status.value, "severity": defect.severity},
    )
    await session.flush()
    response = DefectResponse.model_validate(defect)
    response.observation_count = await repo.observation_count(defect.id)
    return response
