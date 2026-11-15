"""ProcessingJob lifecycle: create, enqueue, retry, cancel."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.application.interfaces.queue import JobQueue
from app.core.exceptions import JobStateError, NotFoundError
from app.domain.enums import AuditAction, JobStatus
from app.domain.processing.state_machine import assert_transition, is_cancellable, is_retryable
from app.infrastructure.database.models.job import ProcessingJob
from app.infrastructure.database.repositories.jobs import JobRepository
from app.infrastructure.database.repositories.uploads import UploadRepository
from app.infrastructure.database.repositories.users import AuditRepository


class JobService:
    def __init__(self, session: AsyncSession, queue: JobQueue) -> None:
        self._session = session
        self._queue = queue
        self._jobs = JobRepository(session)
        self._uploads = UploadRepository(session)
        self._audit = AuditRepository(session)

    async def create_job(
        self,
        *,
        upload_id: uuid.UUID,
        route_id: uuid.UUID | None,
        options: dict | None,
        idempotency_key: str | None,
        actor_id: uuid.UUID | None,
    ) -> tuple[ProcessingJob, bool]:
        if idempotency_key:
            existing = await self._jobs.get_by_idempotency_key(idempotency_key)
            if existing is not None:
                return existing, False
        upload = await self._uploads.get(upload_id)
        if upload is None:
            raise NotFoundError("Upload", upload_id)
        job = ProcessingJob(
            upload_id=upload_id,
            route_id=route_id if route_id is not None else upload.route_id,
            status=JobStatus.PENDING,
            idempotency_key=idempotency_key,
            options=options or {},
        )
        self._jobs.add(job)
        await self._session.flush()
        assert_transition(job.status, JobStatus.QUEUED)
        job.status = JobStatus.QUEUED
        await self._session.commit()
        try:
            rq_id = await self._queue.enqueue_processing(job.id)
        except Exception as exc:
            job.status = JobStatus.FAILED
            job.error_code = "queue_unavailable"
            job.error_message = str(exc)[:500]
            job.finished_at = datetime.now(UTC)
            await self._session.commit()
            raise
        job.rq_job_id = rq_id
        self._audit.record(
            actor_id=actor_id,
            action=AuditAction.CREATE.value,
            entity_type="processing_job",
            entity_id=job.id,
            after_state={"upload_id": str(upload_id), "status": job.status.value},
        )
        await self._session.flush()
        await self._session.refresh(job)
        return job, True

    async def retry_job(self, job_id: uuid.UUID, actor_id: uuid.UUID | None) -> ProcessingJob:
        job = await self._jobs.get_or_raise(job_id)
        if not is_retryable(job.status):
            raise JobStateError(f"Job in status {job.status.value} cannot be retried")
        assert_transition(job.status, JobStatus.QUEUED)
        job.status = JobStatus.QUEUED
        job.error_code = None
        job.error_message = None
        job.progress = 0.0
        job.current_stage = None
        job.finished_at = None
        await self._session.commit()
        rq_id = await self._queue.enqueue_processing(job.id)
        job.rq_job_id = rq_id
        self._audit.record(
            actor_id=actor_id,
            action=AuditAction.JOB_RETRY.value,
            entity_type="processing_job",
            entity_id=job.id,
        )
        await self._session.flush()
        await self._session.refresh(job)
        return job

    async def cancel_job(self, job_id: uuid.UUID, actor_id: uuid.UUID | None) -> ProcessingJob:
        job = await self._jobs.get_or_raise(job_id)
        if not is_cancellable(job.status):
            raise JobStateError(f"Job in status {job.status.value} cannot be cancelled")
        assert_transition(job.status, JobStatus.CANCELLED)
        job.status = JobStatus.CANCELLED
        job.finished_at = datetime.now(UTC)
        self._audit.record(
            actor_id=actor_id,
            action=AuditAction.JOB_CANCEL.value,
            entity_type="processing_job",
            entity_id=job.id,
        )
        await self._session.flush()
        return job
