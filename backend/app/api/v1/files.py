"""Authenticated file access (used by local storage; S3 uses presigned URLs)."""

from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from app.dependencies import CurrentUser, StorageDep

router = APIRouter(prefix="/files", tags=["files"])


@router.get("/{key:path}", summary="Download a stored file (auth required)")
async def get_file(key: str, storage: StorageDep, user: CurrentUser) -> FileResponse:
    metadata = await storage.get_metadata(key)
    tmp = tempfile.NamedTemporaryFile(prefix="mgts-download-", delete=False)  # noqa: SIM115
    tmp.close()
    await storage.download_to_file(key, tmp.name)
    return FileResponse(
        tmp.name,
        media_type=metadata.content_type,
        filename=Path(key).name,
        background=BackgroundTask(lambda: Path(tmp.name).unlink(missing_ok=True)),
    )
