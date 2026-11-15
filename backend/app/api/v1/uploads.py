from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, File, Form, Header, Query, Request, UploadFile
from fastapi.responses import JSONResponse

from app.api.v1.idempotency import idempotent_post
from app.application.interfaces.storage import ObjectStorage
from app.application.services.uploads import UploadService
from app.core.exceptions import ValidationAppError
from app.core.ratelimit import RateLimiter
from app.dependencies import (
    CurrentUser,
    OperatorOrAdmin,
    SessionDep,
    SettingsDep,
    StorageDep,
    get_settings,
)
from app.domain.enums import MediaType
from app.infrastructure.database.models.upload import Upload
from app.infrastructure.database.repositories.uploads import UploadRepository
from app.schemas.common import PageResponse
from app.schemas.uploads import UploadResponse

router = APIRouter(prefix="/uploads", tags=["uploads"])


async def _upload_response(upload: Upload, storage: ObjectStorage) -> dict:
    response = UploadResponse.model_validate(upload)
    try:
        response.presigned_url = await storage.generate_presigned_url(upload.storage_key)
    except Exception:
        response.presigned_url = None
    return response.model_dump(mode="json")


@router.post("", summary="Upload image or video (multipart)")
async def create_upload(
    request: Request,
    session: SessionDep,
    storage: StorageDep,
    settings: SettingsDep,
    user: OperatorOrAdmin,
    file: Annotated[UploadFile, File()],
    route_id: Annotated[uuid.UUID | None, Form()] = None,
    metadata: Annotated[str | None, Form(description="JSON object, e.g. gps_track")] = None,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
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
            stream=file.file,
            filename=file.filename or "upload.bin",
            content_type=file.content_type or "application/octet-stream",
            uploaded_by=user.id,
            route_id=route_id,
            metadata=parsed_metadata,
        )
        body = {
            "upload": await _upload_response(result.upload, storage),
            "created": result.created,
        }
        return (201 if result.created else 200), body

    return await idempotent_post(
        session, user_id=user.id, endpoint="POST /uploads", key=idempotency_key, handler=handler
    )


@router.get("", response_model=PageResponse[UploadResponse], summary="List uploads")
async def list_uploads(
    session: SessionDep,
    storage: StorageDep,
    user: CurrentUser,
    media_type: MediaType | None = None,
    route_id: uuid.UUID | None = None,
    search: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    sort_by: str | None = None,
    order: Literal["asc", "desc"] = "desc",
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
    items = [await _upload_response(upload, storage) for upload in result.items]
    return {
        "items": items,
        "total": result.total,
        "page": result.page,
        "page_size": result.page_size,
        "pages": result.pages,
    }


@router.get("/{upload_id}", summary="Get upload by id")
async def get_upload(
    upload_id: uuid.UUID, session: SessionDep, storage: StorageDep, user: CurrentUser
) -> dict:
    upload = await UploadRepository(session).get_or_raise(upload_id)
    return await _upload_response(upload, storage)


@router.delete("/{upload_id}", status_code=204, summary="Delete upload (no jobs allowed)")
async def delete_upload(
    upload_id: uuid.UUID, session: SessionDep, storage: StorageDep, user: OperatorOrAdmin
) -> None:
    repo = UploadRepository(session)
    upload = await repo.get_or_raise(upload_id)
    await UploadService(session, storage, get_settings()).delete_upload(upload, user.id)
