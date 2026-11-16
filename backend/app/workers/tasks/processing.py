"""RQ task entrypoints. The sync wrapper is what RQ enqueues; it builds an
isolated event loop and providers per task execution. The database engine uses
NullPool worker-side (ARCH-11): connections are never shared across forked RQ
processes; inline execution may reuse the application's Database."""

from __future__ import annotations

import asyncio
import os
import uuid

from app.application.use_cases.processing.pipeline import ProcessingPipeline
from app.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.infrastructure.database.session import Database
from app.infrastructure.ml.factory import build_ml_provider
from app.infrastructure.storage.factory import build_storage

logger = get_logger(__name__)


async def process_upload_job(job_id: str, database: Database | None = None) -> None:
    settings = get_settings()
    os.environ.setdefault("OPENCV_IO_MAX_IMAGE_PIXELS", str(settings.processing_max_image_pixels))
    owns_database = database is None
    if database is None:
        database = Database(settings, null_pool=True)
    storage = build_storage(settings)
    ml = build_ml_provider(settings)
    try:
        pipeline = ProcessingPipeline(database, storage, ml, settings)
        await pipeline.run(uuid.UUID(job_id))
    finally:
        try:
            await ml.close()
        except Exception:
            logger.exception("task_ml_close_failed")
        try:
            await storage.close()
        except Exception:
            logger.exception("task_storage_close_failed")
        if owns_database:
            try:
                await database.dispose()
            except Exception:
                logger.exception("task_database_dispose_failed")


def process_upload_task(job_id: str) -> None:
    settings = get_settings()
    os.environ.setdefault("OPENCV_IO_MAX_IMAGE_PIXELS", str(settings.processing_max_image_pixels))
    configure_logging(settings.log_level, settings.log_format)
    logger.info("task_start", job_id=job_id)
    asyncio.run(process_upload_job(job_id))
