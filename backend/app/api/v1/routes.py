"""Routes API. Writes delegate to RouteService (WKT/ST_Length, audit);
reads use the read-via-repo pattern."""
# ruff: noqa: RUF001  # русскоязычная документация API: кириллица и тире намеренны (ложные срабатывания)

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Path, Query
from fastapi.responses import JSONResponse

from app.api.route import DocumentedRoute
from app.api.v1.idempotency import idempotent_post
from app.api.v1.params import (
    IdempotencyKeyHeader,
    OrderQuery,
    PageQuery,
    PageSizeQuery,
    RouteSort,
    SearchQuery,
    validate_date_range,
)
from app.api.v1.serializers import route_response
from app.application.services.routes import RouteService
from app.dependencies import CurrentUser, OperatorOrAdmin, SessionDep
from app.infrastructure.database.repositories.routes import RouteRepository
from app.schemas.common import PageResponse, page_dict
from app.schemas.routes import RouteCreateRequest, RouteResponse

router = APIRouter(prefix="/routes", tags=["Routes & Inspections"], route_class=DocumentedRoute)


@router.post(
    "",
    status_code=201,
    summary="Создание маршрута объезда",
    description=(
        "Регистрирует маршрут обследования (survey route): имя, транспорт, "
        "время начала/окончания и GPS-трек.\n\n"
        "- **201** — маршрут создан; `total_distance_m` вычисляется PostGIS "
        "(ST_Length по geography, метры), трек хранится как LINESTRING и "
        "возвращается в `track_geojson`.\n"
        "- **409** `idempotency_conflict` — тот же Idempotency-Key с другим payload "
        "(fingerprint = SHA-256 тела запроса); идентичный повтор возвращает "
        "сохранённый ответ (replay).\n"
        "- **422** — трек короче 2 точек или длиннее 10000, точки не вида "
        "[lon, lat], координаты вне диапазонов, finished_at раньше started_at.\n\n"
        "**Порядок координат трека: [longitude, latitude]** (lon/lat, WGS84). "
        "Naive timestamps трактуются как UTC. Маршрут связывает загрузки/jobs "
        "с физическим объездом: передавайте `route_id` в POST /uploads или "
        "POST /jobs; same-route фактор участвует в дедупликации.\n\n"
        "См. docs/api/geospatial.md, docs/api/upload-and-processing.md."
    ),
    responses={201: {"model": RouteResponse, "description": "Маршрут создан (с track_geojson)"}},
)
async def create_route(
    body: RouteCreateRequest,
    session: SessionDep,
    user: OperatorOrAdmin,
    idempotency_key: IdempotencyKeyHeader = None,
) -> JSONResponse:
    async def handler() -> tuple[int, dict]:
        route = await RouteService(session).create_route(
            name=body.name,
            vehicle_id=body.vehicle_id,
            started_at=body.started_at,
            finished_at=body.finished_at,
            track=body.track,
            metadata=body.metadata,
            actor_id=user.id,
        )
        return 201, route_response(route, with_track=True).model_dump(mode="json")

    return await idempotent_post(
        session,
        user_id=user.id,
        endpoint="POST /routes",
        key=idempotency_key,
        handler=handler,
        request_hash=hashlib.sha256(body.model_dump_json().encode()).hexdigest(),
    )


@router.get(
    "",
    response_model=PageResponse[RouteResponse],
    summary="Список маршрутов",
    description=(
        "Постраничный список маршрутов объезда (без трека — для производительности).\n\n"
        "- **200** — envelope `{items, total, page, page_size, pages}`; "
        "`track_geojson` в списке null (запрашивайте карточку маршрута).\n"
        "- `vehicle_id` — точное совпадение идентификатора транспорта.\n"
        "- `search` — подстрока названия маршрута (≤128 символов).\n"
        "- `date_from`/`date_to` фильтруют по **started_at** (включительно); "
        "date_from > date_to → 422.\n"
        "- `sort_by` — whitelist (Literal): `created_at`, `started_at`, `name`, "
        "`total_distance_m`; иначе → 422.\n\n"
        "См. docs/api/pagination-filtering.md, docs/api/geospatial.md."
    ),
)
async def list_routes(
    session: SessionDep,
    user: CurrentUser,
    vehicle_id: Annotated[
        str | None, Query(description="Фильтр по идентификатору транспорта")
    ] = None,
    search: SearchQuery = None,
    date_from: Annotated[
        datetime | None, Query(description="Нижняя граница started_at (ISO 8601, включительно)")
    ] = None,
    date_to: Annotated[
        datetime | None, Query(description="Верхняя граница started_at (ISO 8601, включительно)")
    ] = None,
    page: PageQuery = 1,
    page_size: PageSizeQuery = 20,
    sort_by: Annotated[
        RouteSort | None,
        Query(description="Whitelist: created_at, started_at, name, total_distance_m"),
    ] = None,
    order: OrderQuery = "desc",
) -> dict:
    validate_date_range(date_from, date_to)
    repo = RouteRepository(session)
    stmt = repo.filtered_stmt(
        vehicle_id=vehicle_id, search=search, date_from=date_from, date_to=date_to
    )
    result = await repo.list_paginated(
        stmt, page=page, page_size=page_size, sort_by=sort_by, order=order
    )
    return page_dict(
        [route_response(route).model_dump(mode="json") for route in result.items], result
    )


@router.get(
    "/{route_id}",
    response_model=RouteResponse,
    summary="Карточка маршрута с треком (GeoJSON)",
    description=(
        "Полная карточка маршрута, включая `track_geojson` (LineString, "
        "координаты `[longitude, latitude]`).\n\n"
        "- **200** — RouteResponse с треком и `total_distance_m` (метры).\n"
        "- **404** `not_found` — маршрут не найден.\n\n"
        "Трек готов к прямой передаче в MapLibre source типа geojson. "
        "Связанные загрузки: `/uploads?route_id=...`, job'ы: `/jobs?route_id=...`. "
        "См. docs/api/geospatial.md."
    ),
)
async def get_route(
    route_id: Annotated[uuid.UUID, Path(description="UUID маршрута")],
    session: SessionDep,
    user: CurrentUser,
) -> RouteResponse:
    route = await RouteRepository(session).get_or_raise(route_id)
    return route_response(route, with_track=True)
