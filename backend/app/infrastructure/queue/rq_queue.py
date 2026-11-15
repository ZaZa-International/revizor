"""RQ-backed queue. Tasks are referenced by import path so the API process
does not import worker/pipeline code at enqueue time."""

from __future__ import annotations

import uuid

import anyio
from redis import Redis
from rq import Queue, Retry

from app.config import Settings

PROCESSING_TASK = "app.workers.tasks.processing.process_upload_task"


class RQJobQueue:
    def __init__(self, settings: Settings, connection: Redis | None = None) -> None:
        self._connection = connection or Redis.from_url(settings.redis_url)
        self._queue = Queue(settings.rq_queue_name, connection=self._connection)
        self._timeout = settings.rq_job_timeout
        self._result_ttl = settings.rq_result_ttl
        self._retry_max = settings.rq_retry_max

    async def enqueue_processing(self, job_id: uuid.UUID) -> str | None:
        def _enqueue() -> str:
            job = self._queue.enqueue(
                PROCESSING_TASK,
                str(job_id),
                job_timeout=self._timeout,
                result_ttl=self._result_ttl,
                retry=Retry(max=self._retry_max, interval=[10, 30, 60]),
            )
            return job.id

        return await anyio.to_thread.run_sync(_enqueue)

    async def queue_length(self) -> int:
        return await anyio.to_thread.run_sync(lambda: self._queue.count)

    async def close(self) -> None:
        await anyio.to_thread.run_sync(self._connection.close)
