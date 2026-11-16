"""Defects API. Reads use the read-via-repo pattern; PATCH delegates to
DefectService (domain transition matrix, presence semantics, audit)."""
# ruff: noqa: RUF001  # русскоязычная документация API: кириллица и тире намеренны (ложные срабатывания)

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Path, Query

from app.api.route import DocumentedRoute
from app.api.v1.params import (
    DefectSort,
    OrderQuery,
    PageQuery,
    PageSizeQuery,
    validate_date_range,
)
from app.api.v1.serializers import defect_response, defect_responses
from app.application.services.defects import DefectService
from app.dependencies import CurrentUser, OperatorOrAdmin, SessionDep
from app.domain.enums import DefectStatus
from app.infrastructure.database.repositories.defects import DefectRepository
from app.schemas.assets import DefectPatchRequest, DefectResponse
from app.schemas.common import PageResponse, page_dict

router = APIRouter(prefix="/defects", tags=["Defects & Risk"], route_class=DocumentedRoute)


@router.get(
    "",
    response_model=PageResponse[DefectResponse],
    summary="Список дефектов с фильтрами",
    description=(
        "Реестр дефектов физических объектов с постраничной выдачей.\n\n"
        "- **200** — envelope `{items, total, page, page_size, pages}`; каждый дефект "
        "содержит `observation_count` (число подтверждающих наблюдений).\n"
        "- `status` — OPEN/CONFIRMED/IN_PROGRESS/RESOLVED/REJECTED.\n"
        "- `defect_type` — точное совпадение с типом из реестра (missing_cover, "
        "damaged_cover, well_subsidence, cabinet_damage, cabinet_door_open, "
        "pole_tilt, pole_damage, cable_break, cable_sag, other).\n"
        "- `severity_min`/`severity_max` — диапазон тяжести 1–5 (включительно).\n"
        "- `date_from`/`date_to` фильтруют по **last_detected_at**; "
        "date_from > date_to → 422.\n"
        "- `sort_by` — whitelist (Literal): `created_at`, `last_detected_at`, "
        "`severity`, `status`; иначе → 422.\n\n"
        "Очередь срочных работ: `status=OPEN&severity_min=4`. "
        "См. docs/api/pagination-filtering.md, docs/api/workflows.md."
    ),
)
async def list_defects(
    session: SessionDep,
    user: CurrentUser,
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
    page: PageQuery = 1,
    page_size: PageSizeQuery = 20,
    sort_by: Annotated[
        DefectSort | None,
        Query(description="Whitelist: created_at, last_detected_at, severity, status"),
    ] = None,
    order: OrderQuery = "desc",
) -> dict:
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
    result = await repo.list_paginated(
        stmt, page=page, page_size=page_size, sort_by=sort_by, order=order
    )
    items = await defect_responses(result.items, session)
    return page_dict([item.model_dump(mode="json") for item in items], result)


@router.get(
    "/{defect_id}",
    response_model=DefectResponse,
    summary="Карточка дефекта",
    description=(
        "Полная карточка дефекта: тип, описание, severity 1–5, статус, "
        "даты первого/последнего обнаружения и устранения, `observation_count`.\n\n"
        "- **200** — DefectResponse.\n"
        "- **404** `not_found` — дефект не найден.\n\n"
        "Связанный объект — `asset_id` (карточка `/assets/{asset_id}`); "
        "подтверждающие детекции — `/observations?asset_id=...`. "
        "Управление статусом — `PATCH /defects/{id}`. См. docs/api/workflows.md."
    ),
)
async def get_defect(
    defect_id: Annotated[uuid.UUID, Path(description="UUID дефекта")],
    session: SessionDep,
    user: CurrentUser,
) -> DefectResponse:
    defect = await DefectRepository(session).get_or_raise(defect_id)
    return await defect_response(defect, session)


@router.patch(
    "/{defect_id}",
    response_model=DefectResponse,
    summary="Обновление статуса/тяжести дефекта",
    description=(
        "Операторское обновление дефекта (OPERATOR+) с доменной матрицей переходов.\n\n"
        "- **200** — обновлённый DefectResponse (изменение записано в audit).\n"
        "- **404** `not_found` — дефект не найден.\n"
        "- **422** `validation_error` — недопустимый переход статуса, пустой PATCH, "
        "severity вне 1–5.\n\n"
        "**Матрица переходов:**\n"
        "- OPEN → CONFIRMED / IN_PROGRESS / RESOLVED / REJECTED\n"
        "- CONFIRMED → IN_PROGRESS / RESOLVED\n"
        "- IN_PROGRESS → CONFIRMED / RESOLVED\n"
        "- RESOLVED → OPEN (reopen, очищает resolved_at)\n"
        "- REJECTED — терминальный через API (возврат только через review workflow)\n\n"
        "RESOLVED заполняет `resolved_at`. **Семантика присутствия (exclude_unset):** "
        "явный null `description` очищает описание; отсутствующие поля не меняются. "
        "Автоматические заявки на ремонт по неподтверждённым предсказаниям "
        "не создаются. См. docs/api/workflows.md."
    ),
)
async def patch_defect(
    defect_id: Annotated[uuid.UUID, Path(description="UUID дефекта")],
    body: DefectPatchRequest,
    session: SessionDep,
    user: OperatorOrAdmin,
) -> DefectResponse:
    defect = await DefectService(session).patch_defect(
        defect_id, body.model_dump(exclude_unset=True), actor_id=user.id
    )
    return await defect_response(defect, session)
