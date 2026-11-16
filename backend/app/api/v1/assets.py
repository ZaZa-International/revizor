"""Assets API. Reads use the documented read-via-repo pattern; writes delegate
to AssetService (optimistic locking, risk re-scoring, history, audit)."""
# ruff: noqa: RUF001  # русскоязычная документация API: кириллица и тире намеренны (ложные срабатывания)

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Path, Query

from app.api.route import DocumentedRoute
from app.api.v1.params import (
    AssetSort,
    BboxQuery,
    OrderQuery,
    PageQuery,
    PageSizeQuery,
    SearchQuery,
    validate_date_range,
)
from app.api.v1.serializers import (
    asset_response,
    defect_responses,
    observation_responses,
)
from app.application.services.assets import AssetService
from app.application.services.geospatial import GeospatialService
from app.application.services.history import AssetHistoryService
from app.application.services.risk import RiskScoringService
from app.dependencies import (
    CurrentUser,
    OperatorOrAdmin,
    SessionDep,
    SettingsDep,
    StorageDep,
    can_access_media,
    parse_bbox,
)
from app.domain.enums import GeolocationStatus, LifecycleStatus, PriorityBand
from app.domain.geospatial.models import GeoPoint
from app.infrastructure.database.repositories.assets import AssetRepository
from app.infrastructure.database.repositories.defects import DefectRepository
from app.infrastructure.database.repositories.misc import HistoryRepository
from app.infrastructure.database.repositories.observations import ObservationRepository
from app.schemas.assets import (
    AssetPatchRequest,
    AssetResponse,
    ConditionHistoryResponse,
    DefectResponse,
    NearbyAssetsResponse,
    ObservationResponse,
)
from app.schemas.common import PageResponse, page_dict, page_response

router = APIRouter(prefix="/assets", tags=["Infrastructure Assets"], route_class=DocumentedRoute)


@router.get(
    "",
    response_model=PageResponse[AssetResponse],
    summary="Список активов с фильтрами",
    description=(
        "Реестр физических объектов инфраструктуры (telecom_well, pole, "
        "telecom_cabinet, cable_line, other) с постраничной выдачей.\n\n"
        "- **200** — envelope `{items, total, page, page_size, pages}`.\n"
        "- `asset_type` — точное совпадение с типом из реестра taxonomy.\n"
        "- `bbox` — `min_lon,min_lat,max_lon,max_lat` (порядок lon/lat, WGS84); "
        "невалидный формат → 422.\n"
        "- `date_from`/`date_to` фильтруют по **last_observed_at** (включительно); "
        "date_from > date_to → 422.\n"
        "- `search` — подстрока display_name/external_id (≤128 символов).\n"
        "- `sort_by` — whitelist (Literal): `created_at`, `last_observed_at`, "
        "`current_priority`, `current_severity`, `asset_type`; иначе → 422.\n"
        "- Объекты без GPS имеют `geolocation_status=UNAVAILABLE` и null-координаты; "
        "в map-слои они не попадают, но видны здесь.\n\n"
        "Шаг 6 сценария (после review). См. docs/api/pagination-filtering.md, "
        "docs/api/geospatial.md, docs/api/workflows.md."
    ),
)
async def list_assets(
    session: SessionDep,
    user: CurrentUser,
    asset_type: Annotated[
        str | None,
        Query(description="Тип объекта: telecom_well, pole, telecom_cabinet, cable_line, other"),
    ] = None,
    geolocation_status: Annotated[
        GeolocationStatus | None,
        Query(description="Достоверность геопривязки: CONFIRMED/ESTIMATED/UNAVAILABLE/INVALID"),
    ] = None,
    lifecycle_status: Annotated[
        LifecycleStatus | None,
        Query(description="Жизненный цикл: ACTIVE / INACTIVE / RETIRED / UNKNOWN"),
    ] = None,
    priority_band: Annotated[
        PriorityBand | None,
        Query(
            description="Полоса приоритета: HIGH_PRIORITY / MEDIUM_PRIORITY / "
            "LOW_PRIORITY / NEEDS_REVIEW"
        ),
    ] = None,
    bbox: BboxQuery = None,
    search: SearchQuery = None,
    date_from: Annotated[
        datetime | None,
        Query(description="Нижняя граница last_observed_at (ISO 8601, включительно)"),
    ] = None,
    date_to: Annotated[
        datetime | None,
        Query(description="Верхняя граница last_observed_at (ISO 8601, включительно)"),
    ] = None,
    page: PageQuery = 1,
    page_size: PageSizeQuery = 20,
    sort_by: Annotated[
        AssetSort | None,
        Query(
            description="Whitelist: created_at, last_observed_at, current_priority, "
            "current_severity, asset_type"
        ),
    ] = None,
    order: OrderQuery = "desc",
) -> dict:
    validate_date_range(date_from, date_to)
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
    return page_dict(
        [asset_response(asset).model_dump(mode="json") for asset in result.items], result
    )


@router.get(
    "/nearby",
    response_model=NearbyAssetsResponse,
    summary="Ближайшие активы в радиусе (PostGIS)",
    description=(
        "Поиск ближайших объектов вокруг точки: PostGIS geography "
        "(ST_DWithin + ST_Distance), расстояния в метрах по большому кругу.\n\n"
        "- **200** — `{items, total}`; items отсортированы по возрастанию "
        "`distance_m`, каждый содержит id, asset_type, display_name, distance_m, "
        "current_priority.\n"
        "- **422** — координаты вне диапазонов (lon ∈ [-180,180], lat ∈ [-90,90]), "
        "radius_m вне (0, 5000], limit вне [1, 100].\n\n"
        "Порядок координат: **longitude, latitude**. Активы без координат "
        "в выборку не попадают. Используется для контекста карточки объекта "
        "и проверки дедупликации оператором.\n\n"
        "См. docs/api/geospatial.md."
    ),
)
async def nearby_assets(
    session: SessionDep,
    user: CurrentUser,
    longitude: Annotated[float, Query(ge=-180, le=180, description="Долгота точки поиска (WGS84)")],
    latitude: Annotated[float, Query(ge=-90, le=90, description="Широта точки поиска (WGS84)")],
    radius_m: Annotated[
        float, Query(gt=0, le=5000, description="Радиус поиска в метрах (0 < r ≤ 5000)")
    ] = 50,
    asset_type: Annotated[
        str | None, Query(description="Опциональный фильтр по типу объекта")
    ] = None,
    limit: Annotated[
        int, Query(ge=1, le=100, description="Максимум результатов (1–100, по умолчанию 10)")
    ] = 10,
) -> dict:
    items = await GeospatialService(session).nearest_assets(
        point=GeoPoint(longitude, latitude), radius_m=radius_m, asset_type=asset_type, limit=limit
    )
    return {"items": items, "total": len(items)}


@router.get(
    "/{asset_id}",
    response_model=AssetResponse,
    summary="Карточка актива",
    description=(
        "Полная карточка физического объекта: координаты и достоверность "
        "геопривязки, текущее состояние/severity, приоритет 0–100 с полосой и "
        "машиночитаемыми факторами (`priority_factors`, `priority_policy_version`), "
        "ручной override, жизненный цикл и `version` для оптимистичной блокировки.\n\n"
        "- **200** — AssetResponse.\n"
        "- **404** `not_found` — актив с таким UUID не существует.\n\n"
        "Приоритет — внутренняя risk-политика (не отраслевой стандарт); "
        "NEEDS_REVIEW означает низкую уверенность ML или неразрешённую "
        "дедупликацию. Связанные данные: `/assets/{id}/observations`, "
        "`/assets/{id}/defects`, `/assets/{id}/history`.\n\n"
        "См. docs/api/workflows.md, docs/api/geospatial.md."
    ),
)
async def get_asset(
    asset_id: Annotated[uuid.UUID, Path(description="UUID актива")],
    session: SessionDep,
    user: CurrentUser,
) -> AssetResponse:
    asset = await AssetRepository(session).get_or_raise(asset_id)
    return asset_response(asset)


@router.patch(
    "/{asset_id}",
    response_model=AssetResponse,
    summary="Ручное обновление актива (оптимистичная блокировка)",
    description=(
        "Операторское обновление (OPERATOR+): display_name, external_id, "
        "lifecycle_status, priority_override (+обязательный reason), location.\n\n"
        "- **200** — обновлённый AssetResponse (version увеличена, приоритет "
        "пересчитан, изменение записано в history и audit).\n"
        "- **404** `not_found` — актив не найден.\n"
        "- **409** `conflict` — оптимистичная блокировка: `expected_version` "
        "не совпадает с текущей `version` (конкурентное обновление). "
        "Перечитайте актив и повторите PATCH.\n"
        "- **422** — пустой PATCH (только expected_version), priority_override "
        "без reason, неизвестные значения enum.\n\n"
        "**Семантика присутствия (exclude_unset):** явный null очищает поле; "
        "очистка priority_override очищает и priority_override_reason. "
        "Ручная location меняет geolocation_source на MANUAL. "
        "Исходные ML-предсказания не затираются — только effective-поля актива.\n\n"
        "См. docs/api/workflows.md."
    ),
)
async def patch_asset(
    asset_id: Annotated[uuid.UUID, Path(description="UUID актива")],
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
    response_model=PageResponse[ConditionHistoryResponse],
    summary="История изменений состояния актива",
    description=(
        "Append-only журнал изменений состояния/тяжести/приоритета актива, "
        "новые записи первыми.\n\n"
        "- **200** — envelope `{items, total, page, page_size, pages}`; каждая запись: "
        "`change_source` (ML_PREDICTION/HUMAN_REVIEW/MANUAL_EDIT/SYSTEM), "
        "previous/new значения condition/severity/priority, `is_physical_change` "
        "(физическое изменение vs пересчёт политики), ссылки на observation/review.\n"
        "- **404** `not_found` — актив не найден.\n\n"
        "История не перезаписывается и не удаляется; используется для разбора "
        "«почему приоритет изменился» и аудита решений оператора.\n\n"
        "См. docs/api/workflows.md."
    ),
)
async def asset_history(
    asset_id: Annotated[uuid.UUID, Path(description="UUID актива")],
    session: SessionDep,
    user: CurrentUser,
    page: PageQuery = 1,
    page_size: PageSizeQuery = 20,
) -> dict:
    await AssetRepository(session).get_or_raise(asset_id)
    result = await HistoryRepository(session).paginated(asset_id, page=page, page_size=page_size)
    return page_response(result, ConditionHistoryResponse)


@router.get(
    "/{asset_id}/observations",
    response_model=PageResponse[ObservationResponse],
    summary="Наблюдения актива",
    description=(
        "Все ML-детекции, привязанные к активу (после дедупликации), "
        "в порядке observed_at.\n\n"
        "- **200** — envelope `{items, total, page, page_size, pages}`; "
        "`order` управляет направлением сортировки по observed_at.\n"
        "- **404** `not_found` — актив не найден.\n"
        "- Медиа-ссылки (`image_url`, `crop_url`) — только OPERATOR/SERVICE/ADMIN; "
        "VIEWER получает null.\n\n"
        "Исходные предсказания (object_type/condition_class/severity) сохранены "
        "неизменными; человеческие решения — в effective_* и review_status.\n\n"
        "См. docs/api/workflows.md."
    ),
)
async def asset_observations(
    asset_id: Annotated[uuid.UUID, Path(description="UUID актива")],
    session: SessionDep,
    storage: StorageDep,
    user: CurrentUser,
    page: PageQuery = 1,
    page_size: PageSizeQuery = 20,
    order: OrderQuery = "desc",
) -> dict:
    await AssetRepository(session).get_or_raise(asset_id)
    repo = ObservationRepository(session)
    stmt = repo.filtered_stmt(asset_id=asset_id)
    result = await repo.list_paginated(
        stmt, page=page, page_size=page_size, sort_by="observed_at", order=order
    )
    items = await observation_responses(
        result.items, session, storage, include_media=can_access_media(user)
    )
    return page_dict([item.model_dump(mode="json") for item in items], result)


@router.get(
    "/{asset_id}/defects",
    response_model=PageResponse[DefectResponse],
    summary="Дефекты актива",
    description=(
        "Дефекты физического объекта, новые по last_detected_at первыми.\n\n"
        "- **200** — envelope `{items, total, page, page_size, pages}`; каждый дефект "
        "содержит тип, severity 1–5, статус, даты обнаружения/устранения и "
        "`observation_count` (число подтверждающих наблюдений).\n"
        "- **404** `not_found` — актив не найден.\n\n"
        "Управление статусами — через `PATCH /defects/{id}` (матрица переходов). "
        "См. docs/api/workflows.md."
    ),
)
async def asset_defects(
    asset_id: Annotated[uuid.UUID, Path(description="UUID актива")],
    session: SessionDep,
    user: CurrentUser,
    page: PageQuery = 1,
    page_size: PageSizeQuery = 20,
) -> dict:
    await AssetRepository(session).get_or_raise(asset_id)
    repo = DefectRepository(session)
    stmt = repo.filtered_stmt(asset_id=asset_id)
    result = await repo.list_paginated(
        stmt, page=page, page_size=page_size, sort_by="last_detected_at", order="desc"
    )
    items = await defect_responses(result.items, session)
    return page_dict([item.model_dump(mode="json") for item in items], result)
