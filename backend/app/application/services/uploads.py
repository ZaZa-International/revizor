"""Upload ingestion: validation, checksum dedup, storage, metadata persistence."""

from __future__ import annotations

import hashlib
import re
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

import anyio
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.interfaces.storage import ObjectStorage
from app.config import Settings
from app.core.exceptions import ConflictError, StorageError, ValidationAppError
from app.domain.enums import AuditAction, MediaType, StorageObjectKind
from app.infrastructure.database.models.stored_file import StoredFile
from app.infrastructure.database.models.upload import Upload
from app.infrastructure.database.repositories.uploads import (
    StoredFileRepository,
    UploadRepository,
)
from app.infrastructure.database.repositories.users import AuditRepository

_CHUNK = 1024 * 1024

_MAGIC_SIGNATURES: list[tuple[bytes, int, str, MediaType]] = [
    (b"\xff\xd8\xff", 0, "image/jpeg", MediaType.IMAGE),
    (b"\x89PNG\r\n\x1a\n", 0, "image/png", MediaType.IMAGE),
    (b"RIFF", 0, "image/webp", MediaType.IMAGE),
    (b"\x1a\x45\xdf\xa3", 0, "video/webm", MediaType.VIDEO),
    (b"RIFF", 0, "video/x-msvideo", MediaType.VIDEO),
    (b"ftyp", 4, "video/mp4", MediaType.VIDEO),
]


def sanitize_filename(filename: str) -> str:
    name = Path(filename).name
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._")
    return name[:200] or "upload.bin"


def sniff_media_type(header: bytes) -> tuple[str, MediaType] | None:
    for magic, offset, mime, media in _MAGIC_SIGNATURES:
        if header[offset : offset + len(magic)] == magic:
            if mime == "image/webp" and header[8:12] != b"WEBP":
                continue
            if mime == "video/x-msvideo" and header[8:12] != b"AVI ":
                continue
            if mime == "video/mp4" and header[8:12] == b"qt  ":
                return "video/quicktime", MediaType.VIDEO
            return mime, media
    return None


@dataclass
class UploadResult:
    upload: Upload
    created: bool


class UploadService:
    def __init__(self, session: AsyncSession, storage: ObjectStorage, settings: Settings) -> None:
        self._session = session
        self._storage = storage
        self._settings = settings
        self._uploads = UploadRepository(session)
        self._files = StoredFileRepository(session)
        self._audit = AuditRepository(session)

    def _validate_declared(self, filename: str, content_type: str) -> MediaType:
        suffix = Path(filename).suffix.lower()
        ct = content_type.split(";")[0].strip().lower()
        if suffix in self._settings.allowed_image_extensions:
            if ct not in self._settings.allowed_image_mime_types:
                raise ValidationAppError(
                    f"Content type {ct!r} does not match image extension {suffix!r}"
                )
            return MediaType.IMAGE
        if suffix in self._settings.allowed_video_extensions:
            if ct not in self._settings.allowed_video_mime_types:
                raise ValidationAppError(
                    f"Content type {ct!r} does not match video extension {suffix!r}"
                )
            return MediaType.VIDEO
        raise ValidationAppError(f"File extension {suffix!r} is not allowed")

    async def create_upload(
        self,
        *,
        stream: BinaryIO,
        filename: str,
        content_type: str,
        uploaded_by: uuid.UUID | None,
        route_id: uuid.UUID | None = None,
        metadata: dict | None = None,
    ) -> UploadResult:
        declared_media = self._validate_declared(filename, content_type)
        safe_name = sanitize_filename(filename)

        digest = hashlib.sha256()
        size = 0
        header = b""
        tmp = tempfile.NamedTemporaryFile(prefix="mgts-upload-", delete=False)  # noqa: SIM115
        try:
            while chunk := stream.read(_CHUNK):
                size += len(chunk)
                if size > self._settings.max_upload_size_bytes:
                    raise ValidationAppError(
                        f"File exceeds maximum size of {self._settings.max_upload_size_bytes} bytes"
                    )
                if len(header) < 16:
                    header += chunk[: 16 - len(header)]
                digest.update(chunk)
                tmp.write(chunk)
            tmp.flush()
            if size == 0:
                raise ValidationAppError("Empty file")

            sniffed = sniff_media_type(header)
            if sniffed is None:
                raise ValidationAppError("Unrecognized file format (magic bytes check failed)")
            actual_mime, actual_media = sniffed
            declared_mime = content_type.split(";")[0].strip().lower()
            if actual_media != declared_media or actual_mime != declared_mime:
                raise ValidationAppError(
                    f"Actual content {actual_mime!r} does not match declared {content_type!r}"
                )

            checksum = digest.hexdigest()
            existing = await self._uploads.get_by_checksum(checksum)
            if existing is not None:
                return UploadResult(upload=existing, created=False)

            upload_id = uuid.uuid4()
            storage_key = f"uploads/{upload_id}/{safe_name}"
            try:
                await self._storage.upload_file(storage_key, tmp.name, actual_mime)
            except StorageError:
                raise
            except Exception as exc:
                raise StorageError("Failed to store upload") from exc

            upload = Upload(
                id=upload_id,
                original_filename=safe_name,
                storage_key=storage_key,
                content_type=actual_mime,
                file_size=size,
                checksum_sha256=checksum,
                media_type=actual_media,
                uploaded_by=uploaded_by,
                route_id=route_id,
                metadata_=metadata or {},
            )
            self._uploads.add(upload)
            await self._session.flush()
            self._files.add(
                StoredFile(
                    storage_key=storage_key,
                    kind=StorageObjectKind.ORIGINAL,
                    upload_id=upload_id,
                    content_type=actual_mime,
                    file_size=size,
                    checksum_sha256=checksum,
                    metadata_={"original_filename": filename},
                )
            )
            self._audit.record(
                actor_id=uploaded_by,
                action=AuditAction.CREATE.value,
                entity_type="upload",
                entity_id=upload_id,
                after_state={
                    "filename": safe_name,
                    "file_size": size,
                    "media_type": actual_media.value,
                    "checksum_sha256": checksum,
                },
            )
            await self._session.flush()
            return UploadResult(upload=upload, created=True)
        finally:
            tmp.close()
            await anyio.to_thread.run_sync(lambda: Path(tmp.name).unlink(missing_ok=True))

    async def delete_upload(self, upload: Upload, actor_id: uuid.UUID | None) -> None:
        from sqlalchemy import func, select

        from app.infrastructure.database.models.job import ProcessingJob

        jobs_count = int(
            (
                await self._session.execute(
                    select(func.count(ProcessingJob.id)).where(ProcessingJob.upload_id == upload.id)
                )
            ).scalar_one()
        )
        if jobs_count > 0:
            raise ConflictError("Upload has processing jobs and cannot be deleted")
        await self._storage.delete(upload.storage_key)
        self._audit.record(
            actor_id=actor_id,
            action=AuditAction.DELETE.value,
            entity_type="upload",
            entity_id=upload.id,
            before_state={"storage_key": upload.storage_key},
        )
        await self._uploads.delete(upload)
