"""Exports API: CSV/XLSX downloads with list-endpoint filter parity.

X-Export-Truncated: true signals that the selection hit EXPORT_ROW_LIMIT.
"""
# ruff: noqa: RUF001  # русскоязычная документация API: кириллица и тире намеренны (ложные срабатывания)

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Query
from fastapi.responses import Response

from app.api.route import DocumentedRoute
from app.api.v1.params import BboxQuery, SearchQuery, validate_date_range
from app.application.services.exports import (
    ASSET_COLUMNS,
    DEFECT_COLUMNS,
    EXPORT_ROW_LIMIT,
    OBSERVATION_COLUMNS,
    ExportService,
)
from app.dependencies import CurrentUser, SessionDep, parse_bbox
from app.domain.enums import (
    DeduplicationResult,
    DefectStatus,
    GeolocationStatus,
    LifecycleStatus,
    ObservationReviewStatus,
    PriorityBand,
)
from app.infrastructure.database.repositories.assets import AssetRepository
from app.infrastructure.database.repositories.defects import DefectRepository
from app.infrastructure.database.repositories.observations import ObservationRepository

router = APIRouter(prefix="/exports", tags=["Exports & Reports"], route_class=DocumentedRoute)

ExportFormat = Literal["csv", "xlsx"]

_XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

_EXPORT_CONTENT = {
    "text/csv": {"schema": {"type": "string", "format": "binary"}},
    _XLSX_MEDIA_TYPE: {"schema": {"type": "string", "format": "binary"}},
}

_EXPORT_HEADERS = {
    "X-Export-Truncated": {
        "description": "Присутствует со значением 'true', если выборка упёрлась в лимит "
        "EXPORT_ROW_LIMIT (50 000 строк) и выгрузка усечена",
        "schema": {"type": "string", "enum": ["true"]},
    },
    "Content-Disposition": {
        "description": 'attachment; filename="<entity>-export-<timestamp>.<csv|xlsx>"',
        "schema": {"type": "string"},
    },
}

ExportFormatQuery = Annotated[
    ExportFormat, Query(alias="format", description="Формат выгрузки: csv (UTF-8 с BOM) или xlsx")
]


def _attachment(
    content: bytes, media_type: str, filename: str, *, truncated: bool = False
) -> Response:
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    if truncated:
        headers["X-Export-Truncated"] = "true"
    return Response(content=content, media_type=media_type, headers=headers)


@router.get(
    "/assets",
    summary="Выгрузка активов (CSV/XLSX)",
    description=(
        "Шаг 9 сквозного сценария (login → upload → job → poll → observations → "
        "asset → review → map → **export**). Выгрузка реестра активов файлом.\n\n"
        "- **200** — бинарный файл: `text/csv` (UTF-8 с BOM, Excel-friendly) или "
        "XLSX; `Content-Disposition: attachment`. Колонки включают тип, состояние, "
        "приоритет, полосу, координаты и даты наблюдений.\n"
        "- Фильтры полностью совпадают с `GET /assets` (asset_type, "
        "geolocation_status, lifecycle_status, priority_band, bbox, search, "
        "date_from/date_to по **last_observed_at**) — передавайте фильтры UI "
        "один в один; date_from > date_to → 422.\n"
        "- **Лимит 50 000 строк**: при усечении ответ несёт заголовок "
        "`X-Export-Truncated: true` (порядок строк детерминирован).\n"
        "- Каждая выгрузка фиксируется в audit log (действие EXPORT).\n\n"
        "См. docs/api/pagination-filtering.md, docs/api/workflows.md."
    ),
    response_class=Response,
    responses={
        200: {
            "description": "Файл выгрузки (CSV или XLSX в зависимости от format)",
            "content": _EXPORT_CONTENT,
            "headers": _EXPORT_HEADERS,
        }
    },
)
async def export_assets(
    session: SessionDep,
    user: CurrentUser,
    export_format: ExportFormatQuery = "csv",
    asset_type: Annotated[
        str | None, Query(description="Тип объекта: telecom_well, pole, telecom_cabinet, ...")
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
) -> Response:
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
    service = ExportService(session)
    rows = await service.asset_rows(stmt)
    content, media_type, filename = service.render(
        rows, ASSET_COLUMNS, export_format, entity="assets", actor_id=user.id
    )
    return _attachment(content, media_type, filename, truncated=len(rows) == EXPORT_ROW_LIMIT)


@router.get(
    "/observations",
    summary="Выгрузка наблюдений (CSV/XLSX)",
    description=(
        "Выгрузка ML-детекций файлом для офлайн-анализа и отчётности.\n\n"
        "- **200** — бинарный файл CSV (UTF-8 с BOM) или XLSX; "
        "`Content-Disposition: attachment`. Колонки включают исходное предсказание, "
        "effective-поля, review_status, dedup_result, геопривязку и даты.\n"
        "- Фильтры совпадают с `GET /observations` (asset_id, job_id → "
        "processing_job_id, object_type, review_status, dedup_result, bbox, "
        "date_from/date_to по **observed_at**); date_from > date_to → 422.\n"
        "- **Лимит 50 000 строк**: при усечении — заголовок "
        "`X-Export-Truncated: true`.\n"
        "- Выгрузка фиксируется в audit log.\n\n"
        "См. docs/api/pagination-filtering.md, docs/api/workflows.md."
    ),
    response_class=Response,
    responses={
        200: {
            "description": "Файл выгрузки (CSV или XLSX в зависимости от format)",
            "content": _EXPORT_CONTENT,
            "headers": _EXPORT_HEADERS,
        }
    },
)
async def export_observations(
    session: SessionDep,
    user: CurrentUser,
    export_format: ExportFormatQuery = "csv",
    asset_id: Annotated[uuid.UUID | None, Query(description="Фильтр по UUID актива")] = None,
    job_id: Annotated[
        uuid.UUID | None, Query(description="Фильтр по UUID job (processing_job_id)")
    ] = None,
    object_type: Annotated[
        str | None, Query(description="Исходный тип объекта ML (напр. telecom_well)")
    ] = None,
    review_status: Annotated[
        ObservationReviewStatus | None,
        Query(
            description="Статус проверки: UNREVIEWED / CONFIRMED / REJECTED / CORRECTED / "
            "NEEDS_MORE_INFORMATION"
        ),
    ] = None,
    dedup_result: Annotated[
        DeduplicationResult | None,
        Query(
            description="Результат дедупликации: MATCHED / NEW_ASSET / POSSIBLE_MATCH / AMBIGUOUS"
        ),
    ] = None,
    bbox: BboxQuery = None,
    date_from: Annotated[
        datetime | None, Query(description="Нижняя граница observed_at (ISO 8601, включительно)")
    ] = None,
    date_to: Annotated[
        datetime | None, Query(description="Верхняя граница observed_at (ISO 8601, включительно)")
    ] = None,
) -> Response:
    validate_date_range(date_from, date_to)
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
    service = ExportService(session)
    rows = await service.observation_rows(stmt)
    content, media_type, filename = service.render(
        rows, OBSERVATION_COLUMNS, export_format, entity="observations", actor_id=user.id
    )
    return _attachment(content, media_type, filename, truncated=len(rows) == EXPORT_ROW_LIMIT)


@router.get(
    "/defects",
    summary="Выгрузка дефектов (CSV/XLSX)",
    description=(
        "Выгрузка реестра дефектов файлом (например, очередь срочных работ: "
        "`status=OPEN&severity_min=4&format=xlsx`).\n\n"
        "- **200** — бинарный файл CSV (UTF-8 с BOM) или XLSX; "
        "`Content-Disposition: attachment`. Колонки включают asset_type, priority, "
        "confidence, geolocation, review_status, observation_count.\n"
        "- Фильтры совпадают с `GET /defects` (asset_id, status, defect_type, "
        "severity_min/severity_max, date_from/date_to по **last_detected_at**); "
        "date_from > date_to → 422.\n"
        "- **Лимит 50 000 строк**: при усечении — заголовок "
        "`X-Export-Truncated: true`.\n"
        "- Выгрузка фиксируется в audit log.\n\n"
        "См. docs/api/pagination-filtering.md, docs/api/workflows.md."
    ),
    response_class=Response,
    responses={
        200: {
            "description": "Файл выгрузки (CSV или XLSX в зависимости от format)",
            "content": _EXPORT_CONTENT,
            "headers": _EXPORT_HEADERS,
        }
    },
)
async def export_defects(
    session: SessionDep,
    user: CurrentUser,
    export_format: ExportFormatQuery = "csv",
    asset_id: Annotated[uuid.UUID | None, Query(description="Фильтр по UUID актива")] = None,
    status: Annotated[
        DefectStatus | None,
        Query(description="Статус: OPEN / CONFIRMED / IN_PROGRESS / RESOLVED / REJECTED"),
    ] = None,
    defect_type: Annotated[
        str | None, Query(description="Тип дефекта из реестра taxonomy (напр. missing_cover)")
    ] = None,
    severity_min: Annotated[
        int | None, Query(ge=1, le=5, description="Минимальная тяжесть (1–5, включительно)")
    ] = None,
    severity_max: Annotated[
        int | None, Query(ge=1, le=5, description="Максимальная тяжесть (1–5, включительно)")
    ] = None,
    date_from: Annotated[
        datetime | None,
        Query(description="Нижняя граница last_detected_at (ISO 8601, включительно)"),
    ] = None,
    date_to: Annotated[
        datetime | None,
        Query(description="Верхняя граница last_detected_at (ISO 8601, включительно)"),
    ] = None,
) -> Response:
    validate_date_range(date_from, date_to)
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
    return _attachment(content, media_type, filename, truncated=len(rows) == EXPORT_ROW_LIMIT)
