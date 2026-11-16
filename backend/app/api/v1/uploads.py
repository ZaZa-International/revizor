# ruff: noqa: RUF001  # русскоязычная документация API: кириллица и тире намеренны (ложные срабатывания)
from __future__ import annotations

import json
import uuid
from datetime import datetime
from functools import partial
from typing import Annotated

from fastapi import APIRouter, File, Form, Path, Query, Request, UploadFile
from fastapi.responses import JSONResponse

from app.api.route import DocumentedRoute
from app.api.v1.idempotency import idempotent_post
from app.api.v1.params import (
    IdempotencyKeyHeader,
    OrderQuery,
    PageQuery,
    PageSizeQuery,
    SearchQuery,
)
from app.application.interfaces.storage import ObjectStorage
from app.application.services.uploads import REDACTED_PLACEHOLDER, UploadService
from app.core.exceptions import ValidationAppError
from app.core.ratelimit import RateLimiter
from app.dependencies import (
    CurrentUser,
    OperatorOrAdmin,
    SessionDep,
    SettingsDep,
    StorageDep,
    can_access_media,
    get_settings,
)
from app.domain.enums import MediaType
from app.infrastructure.database.models.upload import Upload
from app.infrastructure.database.models.user import User
from app.infrastructure.database.repositories.uploads import UploadRepository
from app.schemas.common import PageResponse
from app.schemas.uploads import UploadCreateResponse, UploadResponse

router = APIRouter(prefix="/uploads", tags=["Uploads & Media"], route_class=DocumentedRoute)

_READ_CHUNK = 1024 * 1024


def _upload_dict(upload: Upload) -> dict:
    return UploadResponse.model_validate(upload).model_dump(mode="json")


async def _with_presigned_url(upload_body: dict, storage: ObjectStorage, user: User) -> dict:
    if can_access_media(user) and upload_body.get("storage_key") != REDACTED_PLACEHOLDER:
        try:
            upload_body["presigned_url"] = await storage.generate_presigned_url(
                upload_body["storage_key"]
            )
        except Exception:
            upload_body["presigned_url"] = None
    return upload_body


async def _upload_response(upload: Upload, storage: ObjectStorage, user: User) -> dict:
    return await _with_presigned_url(_upload_dict(upload), storage, user)


@router.post(
    "",
    summary="Загрузка изображения/видео (multipart)",
    description=(
        "Шаг 2 сквозного сценария (login → **upload** → job → poll → observations → "
        "asset → review → map → export). Multipart-ингест с тройной проверкой формата: "
        "расширение, declared MIME и magic bytes (jpeg/png/webp; mp4/avi/mov/webm). "
        "Лимит размера — MAX_UPLOAD_SIZE_BYTES (по умолчанию 2 GiB).\n\n"
        "- **201** — новый файл сохранён (`created: true`).\n"
        "- **200** — дубликат по SHA-256 (`created: false`): возвращается существующая "
        "загрузка. Если она принадлежит другому пользователю, ответ редактируется: "
        "`original_filename`/`storage_key` = `[redacted]`, `metadata` = {}, "
        "`uploaded_by`/`route_id` = null, без presigned URL.\n"
        "- **403** — роль VIEWER (загрузка требует OPERATOR/SERVICE/ADMIN).\n"
        "- **409** — конкурентное использование Idempotency-Key.\n"
        "- **413** — превышен лимит тела запроса (body-limit middleware).\n"
        "- **422** — недопустимый формат/несоответствие MIME, невалидный metadata JSON.\n"
        "- **429** — per-user лимит загрузок (RATE_LIMIT_UPLOAD_PER_MINUTE, 30/мин), "
        "`Retry-After` в секундах.\n\n"
        "**Идемпотентность:** заголовок `Idempotency-Key` (≤128 символов); fingerprint "
        "для uploads — checksum файла. Повтор с тем же ключом возвращает сохранённый "
        "ответ; presigned URL перевыпускается при каждом replay (не протухает).\n\n"
        "**GPS:** кладите трек в `metadata` (JSON-строка). Без GPS объекты создаются "
        "со статусом UNAVAILABLE — координаты не выдумываются. Naive timestamps "
        "трактуются как UTC.\n\n"
        "Пример запроса:\n\n"
        "```bash\n"
        "curl -X POST http://localhost:8000/api/v1/uploads \\\n"
        '  -H "Authorization: Bearer $TOKEN" \\\n'
        '  -H "Idempotency-Key: 9a3f1c2e-7b4d-4e8a-9c31-2f5d8b7a1e04" \\\n'
        '  -F "file=@well_0001.jpg;type=image/jpeg" \\\n'
        '  -F "route_id=d4e5f6a7-b8c9-4d0e-1f2a-3b4c5d6e7f80" \\\n'
        '  -F \'metadata={"capture_started_at":"2026-11-15T12:00:00Z",'
        '"gps_track":[{"timestamp":"2026-11-15T12:00:00Z","longitude":37.6173,'
        '"latitude":55.7558,"accuracy_m":4.0,"heading_deg":45,"speed_mps":8}]}'
        "\n```\n\n"
        "См. docs/api/upload-and-processing.md, docs/api/workflows.md."
    ),
    responses={
        200: {
            "model": UploadCreateResponse,
            "description": "Дубликат по checksum (created=false; чужие данные редактируются)",
        },
        201: {"model": UploadCreateResponse, "description": "Новый файл создан (created=true)"},
    },
)
async def create_upload(
    request: Request,
    session: SessionDep,
    storage: StorageDep,
    settings: SettingsDep,
    user: OperatorOrAdmin,
    file: Annotated[UploadFile, File(description="Изображение или видео (multipart-часть file)")],
    route_id: Annotated[
        uuid.UUID | None, Form(description="UUID маршрута объезда (опционально)")
    ] = None,
    metadata: Annotated[
        str | None,
        Form(
            description="JSON-объект метаданных: gps_track [{timestamp, longitude, latitude, "
            "accuracy_m?, heading_deg?, speed_mps?}], capture_started_at и др."
        ),
    ] = None,
    idempotency_key: IdempotencyKeyHeader = None,
) -> JSONResponse:
    limiter = RateLimiter(request.app.state.redis)
    await limiter.check(f"upload:{user.id}", settings.rate_limit_upload_per_minute)
    parsed_metadata: dict = {}
    if metadata:
        try:
            parsed_metadata = json.loads(metadata)
            if not isinstance(parsed_metadata, dict):
                raise ValueError("metadata must be a JSON object")
        except (ValueError, TypeError) as exc:
            raise ValidationAppError(f"Invalid metadata JSON: {exc}") from exc

    async def handler() -> tuple[int, dict]:
        service = UploadService(session, storage, settings)
        result = await service.create_upload(
            read_chunk=partial(file.read, _READ_CHUNK),
            filename=file.filename or "upload.bin",
            content_type=file.content_type or "application/octet-stream",
            uploaded_by=user.id,
            requester_id=user.id,
            requester_role=user.role,
            route_id=route_id,
            metadata=parsed_metadata,
        )
        body = {"upload": _upload_dict(result.upload), "created": result.created}
        return (201 if result.created else 200), body

    response = await idempotent_post(
        session,
        user_id=user.id,
        endpoint="POST /uploads",
        key=idempotency_key,
        handler=handler,
        request_hash=None,
        result_hash=lambda body: body["upload"]["checksum_sha256"],
    )
    body = json.loads(bytes(response.body))
    body["upload"] = await _with_presigned_url(body["upload"], storage, user)
    return JSONResponse(status_code=response.status_code, content=body)


@router.get(
    "",
    response_model=PageResponse[UploadResponse],
    summary="Список загрузок с фильтрами",
    description=(
        "Постраничный список загрузок (общий read-registry; ownership не ограничивает "
        "чтение, но чужие дубликаты могут быть редактированы).\n\n"
        "- **200** — envelope `{items, total, page, page_size, pages}`.\n"
        "- `date_from`/`date_to` фильтруют по **created_at** (включительно); "
        "date_from > date_to → 422.\n"
        "- `search` — подстрока имени файла (≤128 символов, регистронезависимо).\n"
        "- `sort_by` — whitelist: `created_at`, `file_size`, `original_filename`; "
        "неизвестное значение молча откатывается к created_at (поведение v1).\n"
        "- `presigned_url` заполняется только для OPERATOR/SERVICE/ADMIN; "
        "VIEWER получает null (media gating).\n\n"
        "См. docs/api/pagination-filtering.md, docs/api/upload-and-processing.md."
    ),
)
async def list_uploads(
    session: SessionDep,
    storage: StorageDep,
    user: CurrentUser,
    media_type: Annotated[
        MediaType | None, Query(description="Фильтр по типу медиа: IMAGE / VIDEO")
    ] = None,
    route_id: Annotated[
        uuid.UUID | None, Query(description="Фильтр по UUID маршрута объезда")
    ] = None,
    search: SearchQuery = None,
    date_from: Annotated[
        datetime | None, Query(description="Нижняя граница created_at (ISO 8601, включительно)")
    ] = None,
    date_to: Annotated[
        datetime | None, Query(description="Верхняя граница created_at (ISO 8601, включительно)")
    ] = None,
    page: PageQuery = 1,
    page_size: PageSizeQuery = 20,
    sort_by: Annotated[
        str | None,
        Query(description="Whitelist: created_at, file_size, original_filename (иначе created_at)"),
    ] = None,
    order: OrderQuery = "desc",
) -> dict:
    repo = UploadRepository(session)
    stmt = repo.filtered_stmt(
        media_type=media_type,
        route_id=route_id,
        search=search,
        date_from=date_from,
        date_to=date_to,
    )
    result = await repo.list_paginated(
        stmt, page=page, page_size=page_size, sort_by=sort_by, order=order
    )
    items = [await _upload_response(upload, storage, user) for upload in result.items]
    return {
        "items": items,
        "total": result.total,
        "page": result.page,
        "page_size": result.page_size,
        "pages": result.pages,
    }


@router.get(
    "/{upload_id}",
    summary="Загрузка по идентификатору",
    description=(
        "Карточка загрузки: имя файла, ключ хранилища, checksum, размер, тип медиа, "
        "metadata (включая gps_track) и presigned URL для OPERATOR+.\n\n"
        "- **200** — UploadResponse.\n"
        "- **404** `not_found` — загрузка с таким UUID не существует.\n"
        "- VIEWER получает ответ без `presigned_url` (null).\n\n"
        "См. docs/api/upload-and-processing.md."
    ),
    responses={200: {"model": UploadResponse, "description": "Карточка загрузки"}},
)
async def get_upload(
    upload_id: Annotated[uuid.UUID, Path(description="UUID загрузки")],
    session: SessionDep,
    storage: StorageDep,
    user: CurrentUser,
) -> dict:
    upload = await UploadRepository(session).get_or_raise(upload_id)
    return await _upload_response(upload, storage, user)


@router.delete(
    "/{upload_id}",
    status_code=204,
    summary="Удаление загрузки (только без jobs)",
    description=(
        "Удаляет загрузку и объект в хранилище. Право удаления: только загрузивший "
        "пользователь или ADMIN.\n\n"
        "- **204** — удалено, тело ответа пустое.\n"
        "- **403** `permission_denied` — не uploader и не ADMIN; либо роль VIEWER.\n"
        "- **404** `not_found` — загрузка не найдена.\n"
        "- **409** `conflict` — у загрузки есть processing jobs (удаление запрещено "
        "для сохранения целостности истории).\n\n"
        "Объект хранилища удаляется после commit транзакции: сбой commit не оставляет "
        "«висячую» строку без объекта. См. docs/api/upload-and-processing.md."
    ),
    responses={204: {"description": "Загрузка удалена (без тела ответа)"}},
)
async def delete_upload(
    upload_id: Annotated[uuid.UUID, Path(description="UUID загрузки")],
    session: SessionDep,
    storage: StorageDep,
    user: OperatorOrAdmin,
) -> None:
    repo = UploadRepository(session)
    upload = await repo.get_or_raise(upload_id)
    await UploadService(session, storage, get_settings()).delete_upload(upload, user.id, user.role)
