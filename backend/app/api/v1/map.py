"""GeoJSON map layers for MapLibre / any GIS frontend."""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Query

from app.application.services.geospatial import GeospatialService
from app.dependencies import CurrentUser, SessionDep, parse_bbox
from app.domain.enums import DefectStatus

router = APIRouter(prefix="/map", tags=["map"])


@router.get("/assets", summary="Asset layer (GeoJSON FeatureCollection)")
async def map_assets(
    session: SessionDep,
    user: CurrentUser,
    bbox: str | None = Query(None, description="min_lon,min_lat,max_lon,max_lat"),
    asset_type: str | None = None,
    priority_band: str | None = None,
    limit: int = Query(1000, ge=1, le=5000),
) -> dict:
    return await GeospatialService(session).map_assets(
        bbox=parse_bbox(bbox), asset_type=asset_type, priority_band=priority_band, limit=limit
    )


@router.get("/defects", summary="Defect layer (GeoJSON FeatureCollection)")
async def map_defects(
    session: SessionDep,
    user: CurrentUser,
    bbox: str | None = Query(None),
    status: DefectStatus | None = None,
    severity_min: int | None = Query(None, ge=1, le=5),
    limit: int = Query(1000, ge=1, le=5000),
) -> dict:
    return await GeospatialService(session).map_defects(
        bbox=parse_bbox(bbox), status=status, severity_min=severity_min, limit=limit
    )


@router.get("/observations", summary="Observation layer (GeoJSON FeatureCollection)")
async def map_observations(
    session: SessionDep,
    user: CurrentUser,
    bbox: str | None = Query(None),
    job_id: uuid.UUID | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    limit: int = Query(1000, ge=1, le=5000),
) -> dict:
    return await GeospatialService(session).map_observations(
        bbox=parse_bbox(bbox),
        job_id=str(job_id) if job_id else None,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
    )


@router.get("/routes", summary="Route tracks layer (GeoJSON FeatureCollection)")
async def map_routes(
    session: SessionDep, user: CurrentUser, limit: int = Query(100, ge=1, le=1000)
) -> dict:
    return await GeospatialService(session).map_routes(limit=limit)
