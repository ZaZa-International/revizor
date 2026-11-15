from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Query

from app.api.v1.serializers import asset_response, observation_response
from app.application.services.assets import AssetService
from app.application.services.history import AssetHistoryService
from app.application.services.risk import RiskScoringService
from app.dependencies import (
    CurrentUser,
    OperatorOrAdmin,
    SessionDep,
    SettingsDep,
    StorageDep,
    parse_bbox,
)
from app.domain.enums import GeolocationStatus, LifecycleStatus, PriorityBand
from app.infrastructure.database.repositories.assets import AssetRepository
from app.infrastructure.database.repositories.defects import DefectRepository
from app.infrastructure.database.repositories.observations import ObservationRepository
from app.schemas.assets import (
    AssetPatchRequest,
    AssetResponse,
    ConditionHistoryResponse,
    DefectResponse,
    ObservationResponse,
)
from app.schemas.common import PageResponse

router = APIRouter(prefix="/assets", tags=["assets"])


@router.get("", response_model=PageResponse[AssetResponse], summary="List assets with filters")
async def list_assets(
    session: SessionDep,
    user: CurrentUser,
    asset_type: str | None = None,
    geolocation_status: GeolocationStatus | None = None,
    lifecycle_status: LifecycleStatus | None = None,
    priority_band: PriorityBand | None = None,
    bbox: str | None = Query(None, description="min_lon,min_lat,max_lon,max_lat"),
    search: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    sort_by: str | None = None,
    order: Literal["asc", "desc"] = "desc",
) -> dict:
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
    result = await repo.list_paginated(
        stmt, page=page, page_size=page_size, sort_by=sort_by, order=order
    )
    return {
        "items": [asset_response(asset).model_dump(mode="json") for asset in result.items],
        "total": result.total,
        "page": result.page,
        "page_size": result.page_size,
        "pages": result.pages,
    }


@router.get("/nearby", summary="Nearest assets within radius (PostGIS)")
async def nearby_assets(
    session: SessionDep,
    user: CurrentUser,
    longitude: float = Query(ge=-180, le=180),
    latitude: float = Query(ge=-90, le=90),
    radius_m: float = Query(50, gt=0, le=5000),
    asset_type: str | None = None,
    limit: int = Query(10, ge=1, le=100),
) -> dict:
    from app.application.services.geospatial import GeospatialService
    from app.domain.geospatial.models import GeoPoint

    items = await GeospatialService(session).nearest_assets(
        point=GeoPoint(longitude, latitude), radius_m=radius_m, asset_type=asset_type, limit=limit
    )
    return {"items": items, "total": len(items)}


@router.get("/{asset_id}", response_model=AssetResponse, summary="Get asset")
async def get_asset(asset_id: uuid.UUID, session: SessionDep, user: CurrentUser) -> AssetResponse:
    asset = await AssetRepository(session).get_or_raise(asset_id)
    return asset_response(asset)


@router.patch(
    "/{asset_id}", response_model=AssetResponse, summary="Manual asset update (optimistic locking)"
)
async def patch_asset(
    asset_id: uuid.UUID,
    body: AssetPatchRequest,
    session: SessionDep,
    settings: SettingsDep,
    user: OperatorOrAdmin,
) -> AssetResponse:
    service = AssetService(session, RiskScoringService(settings), AssetHistoryService(session))
    values = body.model_dump(exclude_unset=True)
    asset = await service.patch_asset(
        asset_id, values, actor_id=user.id, expected_version=body.expected_version
    )
    return asset_response(asset)


@router.get(
    "/{asset_id}/history",
    response_model=list[ConditionHistoryResponse],
    summary="Condition change history",
)
async def asset_history(
    asset_id: uuid.UUID, session: SessionDep, user: CurrentUser
) -> list[ConditionHistoryResponse]:
    await AssetRepository(session).get_or_raise(asset_id)
    entries = await AssetHistoryService(session).list_for_asset(asset_id)
    return [ConditionHistoryResponse.model_validate(entry) for entry in entries]


@router.get(
    "/{asset_id}/observations",
    response_model=PageResponse[ObservationResponse],
    summary="Asset observations",
)
async def asset_observations(
    asset_id: uuid.UUID,
    session: SessionDep,
    storage: StorageDep,
    user: CurrentUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    order: Literal["asc", "desc"] = "desc",
) -> dict:
    await AssetRepository(session).get_or_raise(asset_id)
    repo = ObservationRepository(session)
    stmt = repo.filtered_stmt(asset_id=asset_id)
    result = await repo.list_paginated(
        stmt, page=page, page_size=page_size, sort_by="observed_at", order=order
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


@router.get(
    "/{asset_id}/defects", response_model=PageResponse[DefectResponse], summary="Asset defects"
)
async def asset_defects(
    asset_id: uuid.UUID,
    session: SessionDep,
    user: CurrentUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> dict:
    await AssetRepository(session).get_or_raise(asset_id)
    repo = DefectRepository(session)
    stmt = repo.filtered_stmt(asset_id=asset_id)
    result = await repo.list_paginated(
        stmt, page=page, page_size=page_size, sort_by="last_detected_at", order="desc"
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
