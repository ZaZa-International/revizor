from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Query
from fastapi.responses import Response

from app.application.services.exports import (
    ASSET_COLUMNS,
    DEFECT_COLUMNS,
    OBSERVATION_COLUMNS,
    ExportService,
)
from app.dependencies import CurrentUser, SessionDep, parse_bbox
from app.domain.enums import DefectStatus, GeolocationStatus, LifecycleStatus, PriorityBand
from app.infrastructure.database.repositories.assets import AssetRepository
from app.infrastructure.database.repositories.defects import DefectRepository
from app.infrastructure.database.repositories.observations import ObservationRepository

router = APIRouter(prefix="/exports", tags=["exports"])

ExportFormat = Literal["csv", "xlsx"]


def _attachment(content: bytes, media_type: str, filename: str) -> Response:
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/assets", summary="Export assets (CSV/XLSX) with filters")
async def export_assets(
    session: SessionDep,
    user: CurrentUser,
    export_format: ExportFormat = Query("csv", alias="format"),
    asset_type: str | None = None,
    geolocation_status: GeolocationStatus | None = None,
    lifecycle_status: LifecycleStatus | None = None,
    priority_band: PriorityBand | None = None,
    bbox: str | None = Query(None),
    search: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> Response:
    repo = AssetRepository(session)
    stmt = repo.filtered_stmt(
        asset_type=asset_type,
        geolocation_status=geolocation_status,
        lifecycle_status=lifecycle_status,
        priority_band=priority_band,
        bbox=parse_bbox(bbox),
        search=search,
        date_from=date_from,
        date_to=date_to,
    )
    service = ExportService(session)
    rows = await service.asset_rows(stmt)
    content, media_type, filename = service.render(
        rows, ASSET_COLUMNS, export_format, entity="assets", actor_id=user.id
    )
    return _attachment(content, media_type, filename)


@router.get("/observations", summary="Export observations (CSV/XLSX) with filters")
async def export_observations(
    session: SessionDep,
    user: CurrentUser,
    export_format: ExportFormat = Query("csv", alias="format"),
    asset_id: uuid.UUID | None = None,
    job_id: uuid.UUID | None = None,
    object_type: str | None = None,
    bbox: str | None = Query(None),
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> Response:
    repo = ObservationRepository(session)
    stmt = repo.filtered_stmt(
        asset_id=asset_id,
        job_id=job_id,
        object_type=object_type,
        bbox=parse_bbox(bbox),
        date_from=date_from,
        date_to=date_to,
    )
    service = ExportService(session)
    rows = await service.observation_rows(stmt)
    content, media_type, filename = service.render(
        rows, OBSERVATION_COLUMNS, export_format, entity="observations", actor_id=user.id
    )
    return _attachment(content, media_type, filename)


@router.get("/defects", summary="Export defects (CSV/XLSX) with filters")
async def export_defects(
    session: SessionDep,
    user: CurrentUser,
    export_format: ExportFormat = Query("csv", alias="format"),
    asset_id: uuid.UUID | None = None,
    status: DefectStatus | None = None,
    defect_type: str | None = None,
    severity_min: int | None = Query(None, ge=1, le=5),
    severity_max: int | None = Query(None, ge=1, le=5),
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> Response:
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
    service = ExportService(session)
    rows = await service.defect_rows(stmt)
    content, media_type, filename = service.render(
        rows, DEFECT_COLUMNS, export_format, entity="defects", actor_id=user.id
    )
    return _attachment(content, media_type, filename)
