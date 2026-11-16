"""Jobs API. Writes delegate to JobService; reads use the read-via-repo pattern."""
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
    JobSort,
    OrderQuery,
    PageQuery,
    PageSizeQuery,
    validate_date_range,
)
from app.application.services.jobs import JobService
from app.dependencies import CurrentUser, OperatorOrAdmin, QueueDep, SessionDep
from app.domain.enums import FrameStatus, JobStatus
from app.infrastructure.database.repositories.jobs import JobFrameRepository, JobRepository
from app.schemas.common import PageResponse, page_response
from app.schemas.uploads import JobCreateRequest, JobFrameResponse, JobResponse

router = APIRouter(prefix="/jobs", tags=["Processing Jobs"], route_class=DocumentedRoute)


@router.post(
    "",
    summary="Создание processing job для загрузки",
    description=(
        "Шаг 3 сквозного сценария (login → upload → **job** → poll → observations → "
        "asset → review → map → export). Ставит загрузку в очередь RQ; тяжёлая "
        "обработка выполняется в worker, не в API.\n\n"
        "- **201** — job создан (PENDING → QUEUED), возвращает JobResponse.\n"
        "- **200** — replay: тот же Idempotency-Key уже использован с идентичным "
        "payload (fingerprint = SHA-256 тела запроса); возвращается сохранённый job.\n"
        "- **404** `not_found` — загрузка не найдена.\n"
        "- **409** `invalid_job_state` — у загрузки уже есть активный job "
        "(PENDING/QUEUED/PROCESSING); параллельная обработка запрещена. "
        "**409** `idempotency_conflict` — тот же ключ с другим payload/upload.\n"
        "- **422** — невалидное тело запроса.\n"
        "- При недоступности очереди job создаётся в статусе FAILED "
        "(`error_code: queue_unavailable`) и может быть перезапущен через retry.\n\n"
        "`route_id` наследуется от загрузки, если не задан явно. `options` — "
        "зарезервированное информационное поле (на обработку пока не влияет).\n\n"
        "Далее опрашивайте `GET /jobs/{id}` каждые 1–2 с до терминального статуса. "
        "См. docs/api/upload-and-processing.md, docs/api/workflows.md."
    ),
    responses={
        200: {
            "model": JobResponse,
            "description": "Replay: идентичный запрос с тем же Idempotency-Key",
        },
        201: {"model": JobResponse, "description": "Job создан и поставлен в очередь"},
    },
)
async def create_job(
    body: JobCreateRequest,
    session: SessionDep,
    queue: QueueDep,
    user: OperatorOrAdmin,
    idempotency_key: IdempotencyKeyHeader = None,
) -> JSONResponse:
    async def handler() -> tuple[int, dict]:
        service = JobService(session, queue)
        job, created = await service.create_job(
            upload_id=body.upload_id,
            route_id=body.route_id,
            options=body.options,
            idempotency_key=idempotency_key,
            actor_id=user.id,
        )
        return (201 if created else 200), JobResponse.model_validate(job).model_dump(mode="json")

    return await idempotent_post(
        session,
        user_id=user.id,
        endpoint="POST /jobs",
        key=idempotency_key,
        handler=handler,
        request_hash=hashlib.sha256(body.model_dump_json().encode()).hexdigest(),
    )


@router.get(
    "",
    response_model=PageResponse[JobResponse],
    summary="Список processing jobs",
    description=(
        "Постраничный список job'ов с фильтрами по статусу, загрузке и маршруту.\n\n"
        "- **200** — envelope `{items, total, page, page_size, pages}`.\n"
        "- `status` — одно из PENDING/QUEUED/PROCESSING/COMPLETED/"
        "PARTIALLY_COMPLETED/FAILED/CANCELLED.\n"
        "- `date_from`/`date_to` фильтруют по **created_at** (включительно); "
        "date_from > date_to → 422.\n"
        "- `sort_by` — whitelist (Literal): `created_at`, `status`, `started_at`, "
        "`finished_at`; неизвестное значение → 422.\n\n"
        "Типичный сценарий: `GET /jobs?upload_id=...` для поиска job'ов загрузки. "
        "См. docs/api/pagination-filtering.md, docs/api/upload-and-processing.md."
    ),
)
async def list_jobs(
    session: SessionDep,
    user: CurrentUser,
    status: Annotated[
        JobStatus | None, Query(description="Фильтр по статусу жизненного цикла job")
    ] = None,
    upload_id: Annotated[uuid.UUID | None, Query(description="Фильтр по UUID загрузки")] = None,
    route_id: Annotated[
        uuid.UUID | None, Query(description="Фильтр по UUID маршрута объезда")
    ] = None,
    date_from: Annotated[
        datetime | None, Query(description="Нижняя граница created_at (ISO 8601, включительно)")
    ] = None,
    date_to: Annotated[
        datetime | None, Query(description="Верхняя граница created_at (ISO 8601, включительно)")
    ] = None,
    page: PageQuery = 1,
    page_size: PageSizeQuery = 20,
    sort_by: Annotated[
        JobSort | None,
        Query(description="Whitelist: created_at, status, started_at, finished_at"),
    ] = None,
    order: OrderQuery = "desc",
) -> dict:
    validate_date_range(date_from, date_to)
    repo = JobRepository(session)
    stmt = repo.filtered_stmt(
        status=status,
        upload_id=upload_id,
        route_id=route_id,
        date_from=date_from,
        date_to=date_to,
    )
    result = await repo.list_paginated(
        stmt, page=page, page_size=page_size, sort_by=sort_by, order=order
    )
    return page_response(result, JobResponse)


@router.get(
    "/{job_id}",
    response_model=JobResponse,
    summary="Статус и прогресс job (polling)",
    description=(
        "Шаг 4 сценария: опрос состояния обработки каждые 1–2 секунды.\n\n"
        "- **200** — JobResponse: `status`, `progress` (0–1), `current_stage`, "
        "счётчики кадров (total/processed/failed/rejected), `error_code`/`error_message`.\n"
        "- **404** `not_found` — job не найден.\n\n"
        "Терминальные статусы: COMPLETED, PARTIALLY_COMPLETED, FAILED, CANCELLED. "
        "При PARTIALLY_COMPLETED смотрите `/jobs/{id}/frames` (REJECTED с reason, "
        "FAILED с code) и предлагайте retry. «Зависшие» PROCESSING (без прогресса "
        "дольше rq_job_timeout + grace) автоматически переводятся в FAILED "
        "stale-sweeper'ом и становятся retryable.\n\n"
        "См. docs/api/upload-and-processing.md, docs/api/workflows.md."
    ),
)
async def get_job(
    job_id: Annotated[uuid.UUID, Path(description="UUID processing job")],
    session: SessionDep,
    user: CurrentUser,
) -> JobResponse:
    job = await JobRepository(session).get_or_raise(job_id)
    return JobResponse.model_validate(job)


@router.get(
    "/{job_id}/frames",
    response_model=PageResponse[JobFrameResponse],
    summary="Покадровые результаты job",
    description=(
        "Постраничные результаты обработки кадров в порядке frame_index.\n\n"
        "- **200** — envelope `{items, total, page, page_size, pages}`; каждый кадр: "
        "`status` (PROCESSED/REJECTED/FAILED/SKIPPED), `reject_reason` для отбракованных "
        "quality gate, `error_code` для ошибок ML/storage, `observed_at` из GPS-трека.\n"
        "- **404** `not_found` — job не найден.\n"
        "- `status` — фильтр по статусу кадра (например, только FAILED для диагностики).\n\n"
        "Используется при PARTIALLY_COMPLETED/FAILED для понимания, какие кадры "
        "требуют внимания. Повторный запуск пропускает уже обработанные кадры "
        "(идемпотентность по UNIQUE(job_id, frame_index)).\n\n"
        "См. docs/api/upload-and-processing.md."
    ),
)
async def get_job_frames(
    job_id: Annotated[uuid.UUID, Path(description="UUID processing job")],
    session: SessionDep,
    user: CurrentUser,
    status: Annotated[
        FrameStatus | None,
        Query(description="Фильтр по статусу кадра: PROCESSED / REJECTED / FAILED / SKIPPED"),
    ] = None,
    page: PageQuery = 1,
    page_size: PageSizeQuery = 20,
) -> dict:
    await JobRepository(session).get_or_raise(job_id)
    result = await JobFrameRepository(session).paginated(
        job_id, page=page, page_size=page_size, status=status
    )
    return page_response(result, JobFrameResponse)


@router.post(
    "/{job_id}/retry",
    response_model=JobResponse,
    summary="Повторный запуск failed/partial job",
    description=(
        "Перезапускает job: статус → QUEUED, счётчики и прогресс сбрасываются, "
        "ошибка очищается. Повторная обработка идемпотентна — уже обработанные "
        "кадры пропускаются (checkpoint), дубли наблюдений не создаются "
        "(UNIQUE по detection_id).\n\n"
        "- **200** — job перезапущен (JobResponse со статусом QUEUED).\n"
        "- **404** `not_found` — job не найден.\n"
        "- **409** `invalid_job_state` — статус не retryable. Допустимы: "
        "FAILED, PARTIALLY_COMPLETED, CANCELLED, а также «зависший» PROCESSING "
        "(без прогресса дольше rq_job_timeout + grace — stale recovery). "
        "Свежий PROCESSING принадлежит живому worker (advisory-lock fencing) "
        "и перезапуску не подлежит.\n"
        "- **409** `invalid_job_state` — у загрузки уже есть другой активный job.\n"
        "- При отказе очереди job компенсируется в FAILED (`queue_unavailable`).\n\n"
        "См. docs/api/upload-and-processing.md (runbook cancel → retry)."
    ),
)
async def retry_job(
    job_id: Annotated[uuid.UUID, Path(description="UUID processing job")],
    session: SessionDep,
    queue: QueueDep,
    user: OperatorOrAdmin,
) -> JobResponse:
    job = await JobService(session, queue).retry_job(job_id, user.id)
    return JobResponse.model_validate(job)


@router.post(
    "/{job_id}/cancel",
    response_model=JobResponse,
    summary="Отмена pending/queued/processing job",
    description=(
        "Кооперативная отмена: статус job → CANCELLED; worker проверяет статус "
        "каждые 10 кадров и останавливается. Уже сохранённые кадры/наблюдения "
        "остаются (частичный результат не откатывается).\n\n"
        "- **200** — job отменён (JobResponse со статусом CANCELLED).\n"
        "- **404** `not_found` — job не найден.\n"
        "- **409** `invalid_job_state` — отмена допустима только для "
        "PENDING/QUEUED/PROCESSING; терминальные статусы отменить нельзя.\n\n"
        "CANCELLED job можно перезапустить через `POST /jobs/{id}/retry`. "
        "Финализация job защищена от гонки cancel/finalize (условный commit).\n\n"
        "См. docs/api/upload-and-processing.md."
    ),
)
async def cancel_job(
    job_id: Annotated[uuid.UUID, Path(description="UUID processing job")],
    session: SessionDep,
    queue: QueueDep,
    user: OperatorOrAdmin,
) -> JobResponse:
    job = await JobService(session, queue).cancel_job(job_id, user.id)
    return JobResponse.model_validate(job)
