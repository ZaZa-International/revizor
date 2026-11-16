"""Job progress/stage tracking and finalization (extracted from the pipeline).

Owns all job-row writes related to progress: stage transitions (throttled),
counter updates, finalize with row locking (REL-8) and failure marking.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from app.core import metrics
from app.core.logging import get_logger
from app.domain.enums import FrameStatus, JobStatus, ProcessingStage
from app.infrastructure.database.models.job import ProcessingJob
from app.infrastructure.database.repositories.jobs import JobFrameRepository
from app.infrastructure.database.session import Database
from sqlalchemy.ext.asyncio import AsyncSession

logger = get_logger(__name__)


class JobProgressTracker:
    def __init__(self, database: Database) -> None:
        self._database = database
        self._last_stage: ProcessingStage | None = None

    @property
    def last_stage(self) -> ProcessingStage | None:
        return self._last_stage

    def reset(self) -> None:
        self._last_stage = None

    async def set_stage(self, job_id: uuid.UUID, stage: ProcessingStage) -> None:
        if self._last_stage == stage:
            return
        self._last_stage = stage
        async with self._database.session() as session:
            job = await session.get(ProcessingJob, job_id)
            if job is not None and job.status == JobStatus.PROCESSING:
                job.current_stage = stage
                await session.commit()

    async def update_progress(
        self, job_id: uuid.UUID, total: int, processed: int, rejected: int, failed: int
    ) -> None:
        async with self._database.session() as session:
            job = await session.get(ProcessingJob, job_id)
            if job is None or job.status == JobStatus.CANCELLED:
                return
            done = processed + rejected + failed
            job.processed_frames = processed
            job.rejected_frames = rejected
            job.failed_frames = failed
            job.total_frames = max(job.total_frames, total, done)
            job.progress = min(1.0, done / total) if total else 0.0
            job.current_stage = ProcessingStage.PERSISTENCE
            await session.commit()

    async def finalize(self, job_id: uuid.UUID, cancelled: bool, started: datetime) -> None:
        async with self._database.session() as session:
            job = await session.get(ProcessingJob, job_id, with_for_update=True)
            if job is None:
                return
            frames_repo = JobFrameRepository(session)
            job.processed_frames = await frames_repo.count_by_status(job_id, FrameStatus.PROCESSED)
            job.rejected_frames = await frames_repo.count_by_status(job_id, FrameStatus.REJECTED)
            job.failed_frames = await frames_repo.count_by_status(job_id, FrameStatus.FAILED)
            job.total_frames = job.processed_frames + job.rejected_frames + job.failed_frames
            if cancelled or job.status == JobStatus.CANCELLED:
                job.status = JobStatus.CANCELLED
            elif job.failed_frames == 0:
                job.status = JobStatus.COMPLETED
            elif job.processed_frames > 0 or job.rejected_frames > 0:
                job.status = JobStatus.PARTIALLY_COMPLETED
                job.error_code = "partial_frame_failures"
                job.error_message = f"{job.failed_frames} frame(s) failed"
            else:
                job.status = JobStatus.FAILED
                job.error_code = "all_frames_failed"
                job.error_message = f"All {job.failed_frames} frame(s) failed"
            job.progress = 1.0
            job.current_stage = ProcessingStage.COMPLETED
            job.finished_at = datetime.now(UTC)
            await session.commit()
        duration = (datetime.now(UTC) - started).total_seconds()
        metrics.JOB_DURATION.labels(job.status.value).observe(duration)
        logger.info(
            "pipeline_finished",
            status=job.status.value,
            processed=job.processed_frames,
            rejected=job.rejected_frames,
            failed=job.failed_frames,
            duration_s=round(duration, 2),
        )

    async def fail_job(
        self,
        session: AsyncSession,
        job: ProcessingJob,
        code: str,
        message: str,
        started_at: datetime,
    ) -> None:
        job.status = JobStatus.FAILED
        job.error_code = code
        job.error_message = message[:1000]
        job.finished_at = datetime.now(UTC)
        job.progress = 1.0
        duration = (datetime.now(UTC) - started_at).total_seconds()
        metrics.JOB_DURATION.labels(JobStatus.FAILED.value).observe(duration)
        logger.error("pipeline_job_failed", code=code, message=message)
