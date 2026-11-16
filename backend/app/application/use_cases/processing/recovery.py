"""Stale-job recovery sweeper (REL-1).

PROCESSING/QUEUED jobs whose updated_at is older than rq_job_timeout + grace
and whose RQ execution is dead (missing, finished, failed, or absent from the
started/queued registries) are marked FAILED so operators can retry them.
Live executions are never touched; pipeline fencing (REL-3) makes the
subsequent retry safe even if the old executor is merely slow.

Runs at worker startup and periodically from a daemon thread; also callable
from tests and maintenance scripts.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import anyio
from app.config import Settings
from app.core.logging import get_logger
from app.domain.enums import JobStatus
from app.infrastructure.database.models.job import ProcessingJob
from app.infrastructure.database.session import Database
from redis import Redis
from redis.exceptions import RedisError
from sqlalchemy import select

logger = get_logger(__name__)

_STALE_STATUSES = (JobStatus.PROCESSING, JobStatus.QUEUED)


def _rq_execution_alive_sync(rq_job_id: str, settings: Settings, connection: Redis | None) -> bool:
    from rq import Queue
    from rq.exceptions import NoSuchJobError
    from rq.job import Job, JobStatus
    from rq.registry import StartedJobRegistry

    owns_connection = connection is None
    conn = connection or Redis.from_url(settings.redis_url)
    try:
        try:
            rq_job = Job.fetch(rq_job_id, connection=conn)
        except NoSuchJobError:
            return False
        if rq_job is None:
            return False
        status = rq_job.get_status()
        if status in {JobStatus.FINISHED, JobStatus.FAILED, JobStatus.STOPPED, JobStatus.CANCELED}:
            return False
        started = StartedJobRegistry(settings.rq_queue_name, connection=conn)
        if rq_job_id in started.get_job_ids():
            return True
        queued = Queue(settings.rq_queue_name, connection=conn)
        return rq_job_id in queued.get_job_ids()
    finally:
        if owns_connection:
            conn.close()


async def rq_execution_alive(
    rq_job_id: str | None, settings: Settings, redis_connection: Redis | None = None
) -> bool:
    if not rq_job_id or rq_job_id.startswith("inline:"):
        return False
    try:
        return await anyio.to_thread.run_sync(
            _rq_execution_alive_sync, rq_job_id, settings, redis_connection
        )
    except RedisError as exc:
        logger.warning("sweeper_redis_unavailable", error=str(exc))
        return True


async def sweep_stale_jobs(
    database: Database, settings: Settings, redis_connection: Redis | None = None
) -> list[uuid.UUID]:
    cutoff = datetime.now(UTC) - timedelta(seconds=settings.stale_job_threshold_seconds)
    async with database.session() as session:
        stmt = select(ProcessingJob).where(
            ProcessingJob.status.in_(_STALE_STATUSES), ProcessingJob.updated_at < cutoff
        )
        stale_jobs = list((await session.execute(stmt)).scalars().all())

    recovered: list[uuid.UUID] = []
    for stale in stale_jobs:
        if await rq_execution_alive(stale.rq_job_id, settings, redis_connection):
            continue
        async with database.session() as session:
            job = await session.get(ProcessingJob, stale.id, with_for_update=True)
            if job is None or job.status not in _STALE_STATUSES or job.updated_at >= cutoff:
                continue
            error_code = (
                "stale_processing" if job.status == JobStatus.PROCESSING else "stale_queued"
            )
            job.status = JobStatus.FAILED
            job.error_code = error_code
            job.error_message = "No live queue execution found; marked failed by recovery sweeper"
            job.finished_at = datetime.now(UTC)
            job.progress = 1.0
            await session.commit()
        recovered.append(stale.id)
        logger.info("stale_job_recovered", job_id=str(stale.id), error_code=error_code)
    return recovered
