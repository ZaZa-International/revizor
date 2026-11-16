"""Wave-1 reliability integration scenarios against real PostGIS/Redis/storage.

Fencing (REL-3), write-ahead reuse (REL-4), active-upload guard (REL-5),
stale retry + sweeper (REL-1/7), cross-upload dedup race (REL-5), finalize
cancel race (REL-8), total_frames reconciliation (REL-13).
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from app.application.services.deduplication import DeduplicationService
from app.application.services.jobs import JobService
from app.application.use_cases.processing.pipeline import ProcessingPipeline
from app.application.use_cases.processing.recovery import sweep_stale_jobs
from app.core.exceptions import JobStateError
from app.domain.enums import DeduplicationResult, FrameStatus, JobStatus
from app.infrastructure.database.models.asset import Asset
from app.infrastructure.database.models.job import JobFrame, ProcessingJob
from app.infrastructure.database.models.observation import Observation
from app.infrastructure.queue.rq_queue import RQJobQueue
from app.infrastructure.storage.local import LocalFilesystemStorage
from app.schemas.ml import MLBBox, MLDetection
from redis import Redis
from sqlalchemy import func, select, text

from tests.fixtures.helpers import create_queued_job, seed_upload_row
from tests.fixtures.media import make_jpeg_bytes, make_video_file, upload_metadata
from tests.fixtures.ml_stub import StubMLProvider

pytestmark = pytest.mark.integration


async def ingest_image(database, storage, settings, *, jpeg: bytes, metadata: dict):
    """Local ingestion helper: seeds upload row + storage object directly,
    independent of UploadService API churn."""
    from app.domain.enums import MediaType
    from app.infrastructure.database.models.upload import Upload as UploadModel

    upload = await seed_upload_row(
        database,
        storage,
        key=f"uploads/{uuid.uuid4()}/frame.jpg",
        content=jpeg,
        media_type=MediaType.IMAGE,
    )
    async with database.session() as session:
        row = await session.get(UploadModel, upload.id)
        row.metadata_ = metadata
        await session.commit()
    return upload


class NoopQueue:
    async def enqueue_processing(self, job_id: uuid.UUID) -> str | None:
        return f"noop:{job_id}"

    async def queue_length(self) -> int:
        return 0

    async def close(self) -> None:
        return None


class FailingQueue:
    async def enqueue_processing(self, job_id: uuid.UUID) -> str | None:
        raise RuntimeError("redis is down")

    async def queue_length(self) -> int:
        return 0

    async def close(self) -> None:
        return None


class SlowStubML(StubMLProvider):
    def __init__(self, delay: float = 0.3, **kwargs) -> None:
        super().__init__(**kwargs)
        self._delay = delay

    async def infer_image(self, request):
        await asyncio.sleep(self._delay)
        return await super().infer_image(request)


class RandomIdStubML(StubMLProvider):
    def __init__(self) -> None:
        super().__init__(factory=self._random_detections)
        self.seen_ids: list[uuid.UUID] = []

    def _random_detections(self, request) -> list[MLDetection]:
        detection = MLDetection(
            detection_id=uuid.uuid4(),
            object_type="telecom_well",
            condition_class="damaged_cover",
            confidence=0.92,
            severity=4,
            bbox=MLBBox(x_min=10, y_min=10, x_max=200, y_max=200),
        )
        self.seen_ids.append(detection.detection_id)
        return [detection]


async def _get_job(database, job_id) -> ProcessingJob:
    async with database.session() as session:
        job = await session.get(ProcessingJob, job_id)
        await session.refresh(job)
        return job


async def _count(database, model, **filters) -> int:
    async with database.session() as session:
        stmt = select(func.count(model.id))
        for column, value in filters.items():
            stmt = stmt.where(getattr(model, column) == value)
        return int((await session.execute(stmt)).scalar_one())


async def _age_job(database, job_id, *, status: str, age_seconds: int, rq_job_id=None) -> None:
    async with database.session() as session:
        await session.execute(
            text(
                "UPDATE processing_jobs SET status = :status, updated_at = :ts, "
                "rq_job_id = :rq_id WHERE id = :id"
            ),
            {
                "status": status,
                "ts": datetime.now(UTC) - timedelta(seconds=age_seconds),
                "rq_id": rq_job_id,
                "id": str(job_id),
            },
        )
        await session.commit()


async def test_fencing_second_concurrent_run_skips(database, settings, tmp_path):
    storage = LocalFilesystemStorage(str(tmp_path / "storage"))
    upload = await ingest_image(
        database, storage, settings, jpeg=make_jpeg_bytes(seed=101), metadata=upload_metadata()
    )
    job = await create_queued_job(database, upload.id)
    ml = SlowStubML(delay=0.4)
    first = ProcessingPipeline(database, storage, ml, settings)
    second = ProcessingPipeline(database, storage, ml, settings)
    await asyncio.gather(first.run(job.id), second.run(job.id))

    finished = await _get_job(database, job.id)
    assert finished.status == JobStatus.COMPLETED
    assert finished.processed_frames == 1
    assert finished.total_frames == 1
    assert ml.calls == 1
    assert await _count(database, Observation, processing_job_id=job.id) == 1
    assert await _count(database, Asset) == 1
    assert await _count(database, JobFrame, job_id=job.id) == 1


async def test_write_ahead_reuse_no_duplicate_observations(
    database, settings, tmp_path, monkeypatch
):
    storage = LocalFilesystemStorage(str(tmp_path / "storage"))
    upload = await ingest_image(
        database, storage, settings, jpeg=make_jpeg_bytes(seed=102), metadata=upload_metadata()
    )
    job = await create_queued_job(database, upload.id)
    ml_first = RandomIdStubML()

    original_match = DeduplicationService.match
    match_calls = {"n": 0}

    async def flaky_match(self, **kwargs):
        match_calls["n"] += 1
        if match_calls["n"] == 1:
            raise RuntimeError("simulated crash after inference commit")
        return await original_match(self, **kwargs)

    monkeypatch.setattr(DeduplicationService, "match", flaky_match)
    pipeline = ProcessingPipeline(database, storage, ml_first, settings)
    await pipeline.run(job.id)
    monkeypatch.undo()

    failed = await _get_job(database, job.id)
    assert failed.status == JobStatus.FAILED
    assert ml_first.calls == 1
    async with database.session() as session:
        frame = (
            await session.execute(select(JobFrame).where(JobFrame.job_id == job.id))
        ).scalar_one()
        assert frame.status == FrameStatus.FAILED
        assert frame.ml_response is not None
    assert await _count(database, Observation, processing_job_id=job.id) == 0

    ml_second = RandomIdStubML()
    resumed = ProcessingPipeline(database, storage, ml_second, settings)
    await resumed.run(job.id)

    finished = await _get_job(database, job.id)
    assert finished.status == JobStatus.COMPLETED
    assert ml_second.calls == 0
    assert await _count(database, Observation, processing_job_id=job.id) == 1
    assert await _count(database, Asset) == 1
    async with database.session() as session:
        observation = (
            await session.execute(
                select(Observation).where(Observation.processing_job_id == job.id)
            )
        ).scalar_one()
        frame = (
            await session.execute(select(JobFrame).where(JobFrame.job_id == job.id))
        ).scalar_one()
        assert observation.detection_id == ml_first.seen_ids[0]
        assert observation.job_frame_id == frame.id
        assert frame.status == FrameStatus.PROCESSED


async def test_active_upload_guard_and_retry_compensation(database, settings, tmp_path):
    storage = LocalFilesystemStorage(str(tmp_path / "storage"))
    upload = await ingest_image(
        database, storage, settings, jpeg=make_jpeg_bytes(seed=103), metadata=upload_metadata()
    )
    async with database.session() as session:
        service = JobService(session, NoopQueue(), settings)
        job, created = await service.create_job(
            upload_id=upload.id, route_id=None, options=None, idempotency_key=None, actor_id=None
        )
        assert created
        job_id = job.id

    async with database.session() as session:
        service = JobService(session, NoopQueue(), settings)
        with pytest.raises(JobStateError):
            await service.create_job(
                upload_id=upload.id,
                route_id=None,
                options=None,
                idempotency_key=str(uuid.uuid4()),
                actor_id=None,
            )

    async with database.session() as session:
        row = await session.get(ProcessingJob, job_id)
        row.status = JobStatus.FAILED
        row.processed_frames = 0
        await session.commit()

    async with database.session() as session:
        service = JobService(session, FailingQueue(), settings)
        with pytest.raises(RuntimeError):
            await service.retry_job(job_id, None)
    compensated = await _get_job(database, job_id)
    assert compensated.status == JobStatus.FAILED
    assert compensated.error_code == "queue_unavailable"
    assert compensated.finished_at is not None

    async with database.session() as session:
        service = JobService(session, NoopQueue(), settings)
        retried = await service.retry_job(job_id, None)
        assert retried.status == JobStatus.QUEUED
        assert retried.processed_frames == 0
        assert retried.rejected_frames == 0
        assert retried.failed_frames == 0
        assert retried.progress == 0.0


async def test_stale_processing_retry_and_fresh_rejected(database, settings, tmp_path):
    storage = LocalFilesystemStorage(str(tmp_path / "storage"))
    upload = await ingest_image(
        database, storage, settings, jpeg=make_jpeg_bytes(seed=104), metadata=upload_metadata()
    )
    stale = await create_queued_job(database, upload.id)
    await _age_job(database, stale.id, status="PROCESSING", age_seconds=7200)
    async with database.session() as session:
        service = JobService(session, NoopQueue(), settings)
        retried = await service.retry_job(stale.id, None)
        assert retried.status == JobStatus.QUEUED

    fresh_upload = await ingest_image(
        database, storage, settings, jpeg=make_jpeg_bytes(seed=105), metadata=upload_metadata()
    )
    fresh = await create_queued_job(database, fresh_upload.id)
    await _age_job(database, fresh.id, status="PROCESSING", age_seconds=1)
    async with database.session() as session:
        service = JobService(session, NoopQueue(), settings)
        with pytest.raises(JobStateError):
            await service.retry_job(fresh.id, None)


async def test_sweeper_marks_dead_stale_jobs_failed(database, settings, tmp_path):
    storage = LocalFilesystemStorage(str(tmp_path / "storage"))
    upload_a = await ingest_image(
        database, storage, settings, jpeg=make_jpeg_bytes(seed=106), metadata=upload_metadata()
    )
    upload_b = await ingest_image(
        database, storage, settings, jpeg=make_jpeg_bytes(seed=116), metadata=upload_metadata()
    )
    upload_c = await ingest_image(
        database, storage, settings, jpeg=make_jpeg_bytes(seed=117), metadata=upload_metadata()
    )
    stale_processing = await create_queued_job(database, upload_a.id)
    await _age_job(
        database,
        stale_processing.id,
        status="PROCESSING",
        age_seconds=7200,
        rq_job_id=str(uuid.uuid4()),
    )
    stale_queued = await create_queued_job(database, upload_b.id)
    await _age_job(database, stale_queued.id, status="QUEUED", age_seconds=7200)
    fresh_processing = await create_queued_job(database, upload_c.id)
    await _age_job(
        database,
        fresh_processing.id,
        status="PROCESSING",
        age_seconds=1,
        rq_job_id=str(uuid.uuid4()),
    )

    connection = Redis.from_url(settings.redis_url)
    try:
        recovered = await sweep_stale_jobs(database, settings, redis_connection=connection)
    finally:
        connection.close()
    assert set(recovered) == {stale_processing.id, stale_queued.id}
    dead_processing = await _get_job(database, stale_processing.id)
    dead_queued = await _get_job(database, stale_queued.id)
    untouched = await _get_job(database, fresh_processing.id)
    assert dead_processing.status == JobStatus.FAILED
    assert dead_processing.error_code == "stale_processing"
    assert dead_processing.finished_at is not None
    assert dead_queued.status == JobStatus.FAILED
    assert dead_queued.error_code == "stale_queued"
    assert untouched.status == JobStatus.PROCESSING


async def test_sweeper_skips_live_rq_execution(database, settings, tmp_path):
    storage = LocalFilesystemStorage(str(tmp_path / "storage"))
    upload = await ingest_image(
        database, storage, settings, jpeg=make_jpeg_bytes(seed=107), metadata=upload_metadata()
    )
    live = await create_queued_job(database, upload.id)
    queue = RQJobQueue(settings)
    connection = Redis.from_url(settings.redis_url)
    try:
        rq_id = await queue.enqueue_processing(uuid.uuid4())
        await _age_job(database, live.id, status="QUEUED", age_seconds=7200, rq_job_id=rq_id)
        recovered = await sweep_stale_jobs(database, settings, redis_connection=connection)
        assert live.id not in recovered
        assert (await _get_job(database, live.id)).status == JobStatus.QUEUED
    finally:
        from rq import Queue

        Queue(settings.rq_queue_name, connection=connection).empty()
        connection.close()
        await queue.close()


async def test_concurrent_cross_upload_dedup_single_asset(database, settings, tmp_path):
    storage = LocalFilesystemStorage(str(tmp_path / "storage"))
    metadata = upload_metadata()
    upload_a = await ingest_image(
        database, storage, settings, jpeg=make_jpeg_bytes(seed=108), metadata=metadata
    )
    upload_b = await ingest_image(
        database, storage, settings, jpeg=make_jpeg_bytes(seed=109), metadata=metadata
    )
    job_a = await create_queued_job(database, upload_a.id)
    job_b = await create_queued_job(database, upload_b.id)
    pipeline_a = ProcessingPipeline(database, storage, SlowStubML(delay=0.2), settings)
    pipeline_b = ProcessingPipeline(database, storage, SlowStubML(delay=0.2), settings)
    await asyncio.gather(pipeline_a.run(job_a.id), pipeline_b.run(job_b.id))

    assert (await _get_job(database, job_a.id)).status == JobStatus.COMPLETED
    assert (await _get_job(database, job_b.id)).status == JobStatus.COMPLETED
    assert await _count(database, Asset) == 1
    assert await _count(database, Observation) == 2
    async with database.session() as session:
        results = (await session.execute(select(Observation.dedup_result))).scalars().all()
        assert set(results) == {DeduplicationResult.NEW_ASSET, DeduplicationResult.MATCHED}
        asset_ids = (await session.execute(select(Observation.asset_id))).scalars().all()
        assert len(set(asset_ids)) == 1


async def test_finalize_preserves_cancelled(database, settings, tmp_path):
    storage = LocalFilesystemStorage(str(tmp_path / "storage"))
    upload = await ingest_image(
        database, storage, settings, jpeg=make_jpeg_bytes(seed=110), metadata=upload_metadata()
    )
    job = await create_queued_job(database, upload.id)

    class CancellingML(StubMLProvider):
        async def infer_image(self, request):
            async with database.session() as session:
                row = await session.get(ProcessingJob, job.id)
                row.status = JobStatus.CANCELLED
                await session.commit()
            return await super().infer_image(request)

    pipeline = ProcessingPipeline(database, storage, CancellingML(), settings)
    await pipeline.run(job.id)
    finished = await _get_job(database, job.id)
    assert finished.status == JobStatus.CANCELLED
    assert finished.processed_frames == 1
    assert finished.total_frames == 1
    assert finished.progress == 1.0


async def test_video_total_frames_reconciled_to_frame_rows(database, settings, tmp_path):
    storage = LocalFilesystemStorage(str(tmp_path / "storage"))
    video_path = str(tmp_path / "survey.mp4")
    make_video_file(video_path, frames=30, fps=10, bad_frame_indices=(10, 11, 12, 13, 14))
    with open(video_path, "rb") as fh:  # noqa: ASYNC230
        content = fh.read()
    from app.domain.enums import MediaType

    upload = await seed_upload_row(
        database,
        storage,
        key=f"uploads/{uuid.uuid4()}/survey.mp4",
        content=content,
        media_type=MediaType.VIDEO,
    )
    async with database.session() as session:
        from app.infrastructure.database.models.upload import Upload as UploadModel

        row = await session.get(UploadModel, upload.id)
        row.metadata_ = upload_metadata()
        await session.commit()
    job = await create_queued_job(database, upload.id)
    pipeline = ProcessingPipeline(database, storage, StubMLProvider(), settings)
    await pipeline.run(job.id)
    finished = await _get_job(database, job.id)
    frame_rows = await _count(database, JobFrame, job_id=job.id)
    assert finished.status == JobStatus.COMPLETED
    assert finished.total_frames == frame_rows
    assert finished.total_frames == (
        finished.processed_frames + finished.rejected_frames + finished.failed_frames
    )
    assert finished.progress == 1.0
