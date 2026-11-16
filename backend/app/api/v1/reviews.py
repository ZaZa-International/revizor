"""Reviews API (append-only). Writes delegate to ReviewService."""
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
    ReviewSort,
    validate_date_range,
)
from app.application.services.history import AssetHistoryService
from app.application.services.reviews import ReviewService
from app.application.services.risk import RiskScoringService
from app.dependencies import CurrentUser, OperatorOrAdmin, SessionDep, SettingsDep
from app.domain.enums import ReviewDecision
from app.domain.reviews.logic import ReviewCorrection
from app.infrastructure.database.repositories.defects import ReviewRepository
from app.schemas.assets import ReviewCreateRequest, ReviewResponse
from app.schemas.common import PageResponse, page_response

router = APIRouter(
    prefix="/reviews", tags=["Reviews & Human-in-the-loop"], route_class=DocumentedRoute
)


@router.post(
    "",
    status_code=201,
    summary="Операторская проверка (append-only review)",
    description=(
        "Шаг 7 сквозного сценария (login → upload → job → poll → observations → "
        "asset → **review** → map → export). Human-in-the-loop: решение оператора "
        "по observation или defect, запись журнала append-only.\n\n"
        "- **201** — review создан и атомарно применён: обновлены "
        "observation.review_status/effective_*, при необходимости defect и asset, "
        "пересчитан приоритет, записана история состояния; CONFIRMED/CORRECTED "
        "создают training examples для ML.\n"
        "- **404** `not_found` — observation/defect не найден.\n"
        "- **409** `idempotency_conflict` — тот же Idempotency-Key с другим payload "
        "(fingerprint = SHA-256 тела запроса).\n"
        "- **422** — нет цели (observation_id/defect_id); CORRECTED без исправлений; "
        "исправления при решении ≠ CORRECTED; неизвестный asset_type/defect_type/"
        "condition; reviewed_at более чем на 5 минут в будущем.\n\n"
        "**Правила corrected_*:** допустимы только при CORRECTED, минимум одно "
        "обязательно. Словарь condition: ok, damaged, damaged_cover, missing_cover, "
        "door_open, tilted, subsided, cable_sag, cable_break, unknown (+алиасы "
        "normal/intact/broken/...); неизвестные метки → 422, молчаливая деградация "
        "в unknown запрещена.\n\n"
        "**Append-only:** повторная проверка создаёт новую запись; история review "
        "не перезаписывается и не удаляется. Исходные ML-предсказания сохраняются. "
        "reviewed_at по умолчанию now(UTC), naive трактуется как UTC.\n\n"
        "См. docs/api/workflows.md, docs/api/errors.md."
    ),
    responses={201: {"model": ReviewResponse, "description": "Review создан и применён"}},
)
async def create_review(
    body: ReviewCreateRequest,
    session: SessionDep,
    settings: SettingsDep,
    user: OperatorOrAdmin,
    idempotency_key: IdempotencyKeyHeader = None,
) -> JSONResponse:
    async def handler() -> tuple[int, dict]:
        service = ReviewService(session, RiskScoringService(settings), AssetHistoryService(session))
        review = await service.create_review(
            observation_id=body.observation_id,
            defect_id=body.defect_id,
            reviewer_id=user.id,
            decision=body.decision,
            correction=ReviewCorrection(
                corrected_asset_type=body.corrected_asset_type,
                corrected_condition=body.corrected_condition,
                corrected_defect_type=body.corrected_defect_type,
                corrected_severity=body.corrected_severity,
            ),
            comment=body.comment,
            reviewed_at=body.reviewed_at,
        )
        return 201, ReviewResponse.model_validate(review).model_dump(mode="json")

    return await idempotent_post(
        session,
        user_id=user.id,
        endpoint="POST /reviews",
        key=idempotency_key,
        handler=handler,
        request_hash=hashlib.sha256(body.model_dump_json().encode()).hexdigest(),
    )


@router.get(
    "",
    response_model=PageResponse[ReviewResponse],
    summary="Список reviews",
    description=(
        "Append-only журнал операторских проверок с фильтрами.\n\n"
        "- **200** — envelope `{items, total, page, page_size, pages}`.\n"
        "- Фильтры: `observation_id`, `defect_id`, `reviewer_id`, `decision` "
        "(CONFIRMED/REJECTED/CORRECTED/NEEDS_MORE_INFORMATION).\n"
        "- `date_from`/`date_to` фильтруют по **reviewed_at** (включительно); "
        "date_from > date_to → 422.\n"
        "- `sort_by` — whitelist (Literal): `reviewed_at`, `created_at`; иначе → 422.\n\n"
        "История проверок одного наблюдения: "
        "`GET /reviews?observation_id=...&sort_by=reviewed_at&order=asc`. "
        "См. docs/api/pagination-filtering.md, docs/api/workflows.md."
    ),
)
async def list_reviews(
    session: SessionDep,
    user: CurrentUser,
    observation_id: Annotated[
        uuid.UUID | None, Query(description="Фильтр по UUID наблюдения")
    ] = None,
    defect_id: Annotated[uuid.UUID | None, Query(description="Фильтр по UUID дефекта")] = None,
    reviewer_id: Annotated[uuid.UUID | None, Query(description="Фильтр по UUID оператора")] = None,
    decision: Annotated[
        ReviewDecision | None,
        Query(description="Решение: CONFIRMED / REJECTED / CORRECTED / NEEDS_MORE_INFORMATION"),
    ] = None,
    date_from: Annotated[
        datetime | None, Query(description="Нижняя граница reviewed_at (ISO 8601, включительно)")
    ] = None,
    date_to: Annotated[
        datetime | None, Query(description="Верхняя граница reviewed_at (ISO 8601, включительно)")
    ] = None,
    page: PageQuery = 1,
    page_size: PageSizeQuery = 20,
    sort_by: Annotated[
        ReviewSort | None, Query(description="Whitelist: reviewed_at, created_at")
    ] = None,
    order: OrderQuery = "desc",
) -> dict:
    validate_date_range(date_from, date_to)
    repo = ReviewRepository(session)
    stmt = repo.filtered_stmt(
        observation_id=observation_id,
        defect_id=defect_id,
        reviewer_id=reviewer_id,
        decision=decision,
        date_from=date_from,
        date_to=date_to,
    )
    result = await repo.list_paginated(
        stmt, page=page, page_size=page_size, sort_by=sort_by, order=order
    )
    return page_response(result, ReviewResponse)


@router.get(
    "/{review_id}",
    response_model=ReviewResponse,
    summary="Карточка review",
    description=(
        "Запись операторской проверки: цель (observation/defect), решение, "
        "исправления corrected_*, комментарий, время проверки и автор.\n\n"
        "- **200** — ReviewResponse.\n"
        "- **404** `not_found` — review не найден.\n\n"
        "Записи append-only: изменение и удаление через API недоступны. "
        "См. docs/api/workflows.md."
    ),
)
async def get_review(
    review_id: Annotated[uuid.UUID, Path(description="UUID review")],
    session: SessionDep,
    user: CurrentUser,
) -> ReviewResponse:
    review = await ReviewRepository(session).get_or_raise(review_id)
    return ReviewResponse.model_validate(review)
