"""Inline queue: executes the processing pipeline in-process.

Used by tests and by `QUEUE_MODE=inline` development runs without a worker.
NOT for production: heavy processing must not run inside HTTP requests.
"""

from __future__ import annotations

import uuid

from app.core.logging import get_logger
from app.infrastructure.database.session import Database

logger = get_logger(__name__)


class InlineJobQueue:
    def __init__(self, database: Database | None = None) -> None:
        self._database = database

    async def enqueue_processing(self, job_id: uuid.UUID) -> str | None:
        from app.workers.tasks.processing import process_upload_job

        logger.info("inline_processing_start", job_id=str(job_id))
        await process_upload_job(str(job_id), database=self._database)
        return f"inline:{job_id}"

    async def queue_length(self) -> int:
        return 0

    async def close(self) -> None:
        return None
