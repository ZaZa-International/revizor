"""GeoJSON map layers for MapLibre / any GIS frontend (read-via-service)."""
# ruff: noqa: RUF001  # русскоязычная документация API: кириллица и тире намеренны (ложные срабатывания)

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Query

from app.api.route import DocumentedRoute
from app.api.v1.params import BboxQuery, validate_date_range
from app.application.services.geospatial import GeospatialService
from app.dependencies import CurrentUser, SessionDep, parse_bbox
from app.domain.enums import DefectStatus, PriorityBand
from app.schemas.geo import (
    AssetMapProperties,
    DefectMapProperties,
    FeatureCollection,
    ObservationMapProperties,
    RouteMapProperties,
)

router = APIRouter(prefix="/map", tags=["Geospatial & Maps"], route_class=DocumentedRoute)


@router.get(
    "/assets",
    response_model=FeatureCollection[AssetMapProperties],
    summary="Слой активов (GeoJSON FeatureCollection)",
    description=(
        "Шаг 8 сквозного сценария (login → upload → job → poll → observations → "
        "asset → review → **map** → export). Слой активов для MapLibre/любого "
        "GIS-frontend: типизированный GeoJSON FeatureCollection (RFC 7946).\n\n"
        "- **200** — `{type: FeatureCollection, features: [...]}`; геометрия Point, "
        "координаты строго `[longitude, latitude]` (WGS84). Properties: id, "
        "asset_type, display_name, current_condition/severity/priority, "
        "priority_band, geolocation_status, location_accuracy_m, lifecycle_status, "
        "last_observed_at.\n"
        "- `bbox` — `min_lon,min_lat,max_lon,max_lat` (порядок lon/lat); "
        "невалидный формат → 422.\n"
        "- `priority_band` — типизированный enum (невалидное значение → 422).\n"
        "- `limit` — 1–5000 (по умолчанию 1000); выборка детерминирована "
        "(current_priority desc nulls last, id asc).\n\n"
        "Объекты без GPS (geolocation_status=UNAVAILABLE) в слой не попадают — "
        "показывайте их в списочном представлении `/assets`. "
        "См. docs/api/geospatial.md, docs/api/workflows.md."
    ),
)
async def map_assets(
    session: SessionDep,
    user: CurrentUser,
    bbox: BboxQuery = None,
    asset_type: Annotated[
        str | None, Query(description="Фильтр по типу объекта (напр. telecom_well)")
    ] = None,
    priority_band: Annotated[
        PriorityBand | None,
        Query(
            description="Полоса приоритета: HIGH_PRIORITY / MEDIUM_PRIORITY / "
            "LOW_PRIORITY / NEEDS_REVIEW"
        ),
    ] = None,
    limit: Annotated[
        int, Query(ge=1, le=5000, description="Максимум объектов слоя (1–5000, по умолчанию 1000)")
    ] = 1000,
) -> dict:
    return await GeospatialService(session).map_assets(
        bbox=parse_bbox(bbox), asset_type=asset_type, priority_band=priority_band, limit=limit
    )


@router.get(
    "/defects",
    response_model=FeatureCollection[DefectMapProperties],
    summary="Слой дефектов (GeoJSON FeatureCollection)",
    description=(
        "Слой дефектов для карты: точка актива с атрибутами дефекта.\n\n"
        "- **200** — FeatureCollection; геометрия Point `[lon, lat]`. Properties: "
        "id, asset_id, asset_type, defect_type, severity, status, current_priority, "
        "first/last_detected_at.\n"
        "- `bbox` — `min_lon,min_lat,max_lon,max_lat`; невалидный формат → 422.\n"
        "- `status` — OPEN/CONFIRMED/IN_PROGRESS/RESOLVED/REJECTED.\n"
        "- `severity_min` — нижняя граница тяжести 1–5.\n"
        "- `limit` — 1–5000 (по умолчанию 1000); выборка детерминирована "
        "(severity desc, id asc).\n\n"
        "Дефекты наследуют координаты актива; активы без GPS не отображаются. "
        "См. docs/api/geospatial.md."
    ),
)
async def map_defects(
    session: SessionDep,
    user: CurrentUser,
    bbox: BboxQuery = None,
    status: Annotated[
        DefectStatus | None,
        Query(description="Статус дефекта: OPEN / CONFIRMED / IN_PROGRESS / RESOLVED / REJECTED"),
    ] = None,
    severity_min: Annotated[
        int | None, Query(ge=1, le=5, description="Минимальная тяжесть (1–5, включительно)")
    ] = None,
    limit: Annotated[
        int, Query(ge=1, le=5000, description="Максимум объектов слоя (1–5000, по умолчанию 1000)")
    ] = 1000,
) -> dict:
    return await GeospatialService(session).map_defects(
        bbox=parse_bbox(bbox), status=status, severity_min=severity_min, limit=limit
    )


@router.get(
    "/observations",
    response_model=FeatureCollection[ObservationMapProperties],
    summary="Слой наблюдений (GeoJSON FeatureCollection)",
    description=(
        "Слой ML-детекций для карты (например, результат конкретного job).\n\n"
        "- **200** — FeatureCollection; геометрия Point `[lon, lat]`. Properties: "
        "id, asset_id, object_type, condition_class, detector_confidence, "
        "review_status, dedup_result, observed_at, processing_job_id.\n"
        "- `job_id` — UUID job (фильтр по processing_job_id).\n"
        "- `date_from`/`date_to` фильтруют по **observed_at** (включительно); "
        "date_from > date_to → 422.\n"
        "- `bbox` — `min_lon,min_lat,max_lon,max_lat`; `limit` — 1–5000 "
        "(выборка детерминирована: observed_at desc, id asc).\n\n"
        "Наблюдения без геопривязки в слой не попадают. "
        "См. docs/api/geospatial.md, docs/api/upload-and-processing.md."
    ),
)
async def map_observations(
    session: SessionDep,
    user: CurrentUser,
    bbox: BboxQuery = None,
    job_id: Annotated[
        uuid.UUID | None, Query(description="Фильтр по UUID job (processing_job_id)")
    ] = None,
    date_from: Annotated[
        datetime | None, Query(description="Нижняя граница observed_at (ISO 8601, включительно)")
    ] = None,
    date_to: Annotated[
        datetime | None, Query(description="Верхняя граница observed_at (ISO 8601, включительно)")
    ] = None,
    limit: Annotated[
        int, Query(ge=1, le=5000, description="Максимум объектов слоя (1–5000, по умолчанию 1000)")
    ] = 1000,
) -> dict:
    validate_date_range(date_from, date_to)
    return await GeospatialService(session).map_observations(
        bbox=parse_bbox(bbox),
        job_id=str(job_id) if job_id else None,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
    )


@router.get(
    "/routes",
    response_model=FeatureCollection[RouteMapProperties],
    summary="Слой треков маршрутов (GeoJSON FeatureCollection)",
    description=(
        "Слой треков объездов для карты: геометрия LineString из PostGIS.\n\n"
        "- **200** — FeatureCollection; координаты трека — упорядоченные пары "
        "`[longitude, latitude]`. Properties: id, name, vehicle_id, "
        "started_at/finished_at, total_distance_m (метры, ST_Length).\n"
        "- `bbox` — `min_lon,min_lat,max_lon,max_lat` (пересечение трека с bbox); "
        "невалидный формат → 422.\n"
        "- `date_from`/`date_to` фильтруют по **started_at** (включительно); "
        "date_from > date_to → 422.\n"
        "- `limit` — 1–1000 (по умолчанию 100); выборка детерминирована "
        "(started_at desc, id asc).\n\n"
        "Маршруты без трека в слой не попадают. Используется вместе "
        "со слоем наблюдений для визуализации покрытия объезда. "
        "См. docs/api/geospatial.md."
    ),
)
async def map_routes(
    session: SessionDep,
    user: CurrentUser,
    bbox: BboxQuery = None,
    date_from: Annotated[
        datetime | None, Query(description="Нижняя граница started_at (ISO 8601, включительно)")
    ] = None,
    date_to: Annotated[
        datetime | None, Query(description="Верхняя граница started_at (ISO 8601, включительно)")
    ] = None,
    limit: Annotated[
        int, Query(ge=1, le=1000, description="Максимум маршрутов (1–1000, по умолчанию 100)")
    ] = 100,
) -> dict:
    validate_date_range(date_from, date_to)
    return await GeospatialService(session).map_routes(
        bbox=parse_bbox(bbox), date_from=date_from, date_to=date_to, limit=limit
    )
