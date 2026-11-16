"""Observations API (read-via-repo pattern; media URLs gated by role)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Path, Query

from app.api.route import DocumentedRoute
from app.api.v1.params import (
    BboxQuery,
    ObservationSort,
    OrderQuery,
    PageQuery,
    PageSizeQuery,
    validate_date_range,
)
from app.api.v1.serializers import observation_response, observation_responses
from app.dependencies import CurrentUser, SessionDep, StorageDep, can_access_media, parse_bbox
from app.domain.enums import DeduplicationResult, ObservationReviewStatus
from app.infrastructure.database.repositories.observations import ObservationRepository
from app.schemas.assets import ObservationResponse
from app.schemas.common import PageResponse, page_dict

router = APIRouter(prefix="/observations", tags=["Observations"], route_class=DocumentedRoute)


@router.get(
    "",
    response_model=PageResponse[ObservationResponse],
    summary="Список наблюдений (очередь review)",
    description=(
        "ML-детекции объектов на кадрах — основной рабочий список оператора.\n\n"
        "- **200** — envelope `{items, total, page, page_size, pages}`.\n"
        "- Очередь проверки: `review_status=UNREVIEWED`; неразрешённые совпадения "
        "дедупликации: `dedup_result=POSSIBLE_MATCH` (или AMBIGUOUS).\n"
        "- **Маппинг параметра:** query-параметр `job_id` фильтрует по полю "
        "`processing_job_id` в ответе (API-22).\n"
        "- `date_from`/`date_to` фильтруют по **observed_at** (включительно); "
        "date_from > date_to → 422.\n"
        "- `bbox` — `min_lon,min_lat,max_lon,max_lat` (порядок lon/lat).\n"
        "- `sort_by` — whitelist (Literal): `observed_at`, `created_at`, "
        "`detector_confidence`; иначе → 422.\n"
        "- **VIEWER media gating:** `image_url`/`crop_url` = null для VIEWER; "
        "OPERATOR/SERVICE/ADMIN получают presigned (S3) или /files-ссылки.\n\n"
        "Исходное предсказание (object_type/condition_class/severity/"
        "detector_confidence) не затирается; человеческое решение — effective_* "
        "и review_status. Шаг 5 сценария. См. docs/api/workflows.md, "
        "docs/api/upload-and-processing.md."
    ),
)
async def list_observations(
    session: SessionDep,
    storage: StorageDep,
    user: CurrentUser,
    asset_id: Annotated[uuid.UUID | None, Query(description="Фильтр по UUID актива")] = None,
    job_id: Annotated[
        uuid.UUID | None,
        Query(description="Фильтр по UUID job (поле processing_job_id в ответе)"),
    ] = None,
    object_type: Annotated[
        str | None, Query(description="Фильтр по исходному типу объекта ML (напр. telecom_well)")
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
    page: PageQuery = 1,
    page_size: PageSizeQuery = 20,
    sort_by: Annotated[
        ObservationSort | None,
        Query(description="Whitelist: observed_at, created_at, detector_confidence"),
    ] = None,
    order: OrderQuery = "desc",
) -> dict:
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
    result = await repo.list_paginated(
        stmt, page=page, page_size=page_size, sort_by=sort_by, order=order
    )
    items = await observation_responses(
        result.items, session, storage, include_media=can_access_media(user)
    )
    return page_dict([item.model_dump(mode="json") for item in items], result)


@router.get(
    "/{observation_id}",
    response_model=ObservationResponse,
    summary="Карточка наблюдения",
    description=(
        "Полная карточка ML-детекции для экрана проверки оператора.\n\n"
        "- **200** — ObservationResponse: исходное предсказание, bbox в абсолютных "
        "пикселях исходного кадра {x_min, y_min, x_max, y_max}, размеры кадра, "
        "геопривязка, tracking_id, модель/версия, результат и машиночитаемое "
        "объяснение дедупликации (`dedup_explanation`: кандидаты, веса, пороги, margin).\n"
        "- **404** `not_found` — наблюдение не найдено.\n"
        "- `image_url`/`crop_url`: presigned S3 или `/api/v1/files/...`; "
        "для VIEWER — null (media gating).\n\n"
        "Решение оператора отправляется через `POST /reviews` "
        "(observation_id). Raw ML payload не отдаётся. См. docs/api/workflows.md."
    ),
)
async def get_observation(
    observation_id: Annotated[uuid.UUID, Path(description="UUID наблюдения")],
    session: SessionDep,
    storage: StorageDep,
    user: CurrentUser,
) -> ObservationResponse:
    observation = await ObservationRepository(session).get_or_raise(observation_id)
    return await observation_response(
        observation, session, storage, include_media=can_access_media(user)
    )
