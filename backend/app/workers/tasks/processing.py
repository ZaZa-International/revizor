"""RQ task entrypoints. The sync wrapper is what RQ enqueues; it builds an
isolated event loop, database engine and providers per task execution."""

from __future__ import annotations

import asyncio

from app.application.use_cases.processing.pipeline import ProcessingPipeline
from app.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.infrastructure.database.session import Database
from app.infrastructure.ml.factory import build_ml_provider
from app.infrastructure.storage.factory import build_storage

logger = get_logger(__name__)


async def process_upload_job(job_id: str) -> None:
    import uuid

    settings = get_settings()
    database = Database(settings)
    storage = build_storage(settings)
    ml = build_ml_provider(settings)
    try:
        pipeline = ProcessingPipeline(database, storage, ml, settings)
        await pipeline.run(uuid.UUID(job_id))
    finally:
        await ml.close()
        await storage.close()
        await database.dispose()


def process_upload_task(job_id: str) -> None:
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_format)
    logger.info("task_start", job_id=job_id)
    asyncio.run(process_upload_job(job_id))
