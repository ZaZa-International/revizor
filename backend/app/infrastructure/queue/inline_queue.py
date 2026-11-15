"""Inline queue: executes the processing pipeline in-process.

Used by tests and by `QUEUE_MODE=inline` development runs without a worker.
NOT for production: heavy processing must not run inside HTTP requests.
"""

from __future__ import annotations

import uuid

from app.core.logging import get_logger

logger = get_logger(__name__)


class InlineJobQueue:
    async def enqueue_processing(self, job_id: uuid.UUID) -> str | None:
        from app.workers.tasks.processing import process_upload_job

        logger.info("inline_processing_start", job_id=str(job_id))
        await process_upload_job(str(job_id))
        return f"inline:{job_id}"

    async def queue_length(self) -> int:
        return 0

    async def close(self) -> None:
        return None
