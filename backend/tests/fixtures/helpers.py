"""DB/storage seeding helpers for integration tests."""

from __future__ import annotations

import io
import uuid
from datetime import UTC, datetime

from app.application.interfaces.storage import ObjectStorage
from app.application.services.uploads import UploadService
from app.config import Settings
from app.domain.enums import JobStatus, MediaType
from app.infrastructure.database.models.job import ProcessingJob
from app.infrastructure.database.models.upload import Upload
from app.infrastructure.database.session import Database


async def ingest_image(
    database: Database,
    storage: ObjectStorage,
    settings: Settings,
    *,
    jpeg: bytes,
    metadata: dict,
    filename: str = "frame.jpg",
) -> Upload:
    async with database.session() as session:
        service = UploadService(session, storage, settings)
        result = await service.create_upload(
            stream=io.BytesIO(jpeg),
            filename=filename,
            content_type="image/jpeg",
            uploaded_by=None,
            metadata=metadata,
        )
        await session.commit()
        return result.upload


async def create_queued_job(database: Database, upload_id: uuid.UUID) -> ProcessingJob:
    async with database.session() as session:
        job = ProcessingJob(upload_id=upload_id, status=JobStatus.QUEUED)
        session.add(job)
        await session.commit()
        await session.refresh(job)
        return job


async def seed_upload_row(
    database: Database, storage: ObjectStorage, *, key: str, content: bytes, media_type: MediaType
) -> Upload:
    await storage.upload(key, content, "image/jpeg")
    async with database.session() as session:
        upload = Upload(
            original_filename=key.split("/")[-1],
            storage_key=key,
            content_type="image/jpeg",
            file_size=len(content),
            checksum_sha256=uuid.uuid4().hex + uuid.uuid4().hex,
            media_type=media_type,
            metadata_={},
        )
        session.add(upload)
        await session.commit()
        await session.refresh(upload)
        return upload


def now() -> datetime:
    return datetime.now(UTC)
