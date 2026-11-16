"""Authenticated file access (used by local storage; S3 uses presigned URLs)."""
# ruff: noqa: RUF001  # русскоязычная документация API: кириллица и тире намеренны (ложные срабатывания)

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Annotated

import anyio
from fastapi import APIRouter
from fastapi import Path as PathParam
from fastapi.responses import FileResponse, Response
from starlette.background import BackgroundTask

from app.api.route import DocumentedRoute
from app.core.exceptions import PermissionDeniedError
from app.dependencies import CurrentUser, StorageDep, can_access_media

router = APIRouter(prefix="/files", tags=["Storage & Files"], route_class=DocumentedRoute)


@router.get(
    "/{key:path}",
    summary="Скачивание файла хранилища (OPERATOR+)",
    description=(
        "Аутентифицированное скачивание объекта по storage key — используется при "
        "local storage backend (ссылки `image_url`/`crop_url` указывают сюда).\n\n"
        "- **200** — бинарное содержимое файла (`application/octet-stream` в контракте; "
        "фактический Content-Type берётся из метаданных объекта, например image/jpeg), "
        "`Content-Disposition` с именем файла.\n"
        "- **403** `permission_denied` — роль VIEWER: доступ к медиа только "
        "OPERATOR/SERVICE/ADMIN.\n"
        "- **404** `storage_object_not_found` — объект с таким ключом отсутствует.\n\n"
        "При S3-бэкенде используйте presigned URL напрямую (`presigned_url`, "
        "`image_url`, `crop_url`) — срок жизни ограничен (по умолчанию 3600 с), "
        "перевыпуск происходит при повторном чтении сущности. Ключ содержит "
        "слеши — передавайте его как есть (path-параметр).\n\n"
        "См. docs/api/upload-and-processing.md, docs/api/authentication.md."
    ),
    response_class=Response,
    responses={
        200: {
            "description": "Бинарное содержимое файла",
            "content": {
                "application/octet-stream": {"schema": {"type": "string", "format": "binary"}}
            },
        }
    },
)
async def get_file(
    key: Annotated[str, PathParam(description="Storage key объекта (может содержать слеши)")],
    storage: StorageDep,
    user: CurrentUser,
) -> FileResponse:
    if not can_access_media(user):
        raise PermissionDeniedError("Media access requires OPERATOR, SERVICE or ADMIN role")
    metadata = await storage.get_metadata(key)
    tmp = tempfile.NamedTemporaryFile(prefix="mgts-download-", delete=False)  # noqa: SIM115
    tmp.close()
    try:
        await storage.download_to_file(key, tmp.name)
    except Exception:
        await anyio.to_thread.run_sync(lambda: Path(tmp.name).unlink(missing_ok=True))
        raise
    return FileResponse(
        tmp.name,
        media_type=metadata.content_type,
        filename=Path(key).name,
        background=BackgroundTask(lambda: Path(tmp.name).unlink(missing_ok=True)),
    )
