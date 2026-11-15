"""End-to-end pipeline tests against real PostGIS + local storage."""

from __future__ import annotations

import uuid

import pytest
from app.application.use_cases.processing.pipeline import ProcessingPipeline
from app.core.exceptions import MLTimeoutError, StorageError
from app.domain.enums import (
    DeduplicationResult,
    FrameStatus,
    GeolocationStatus,
    JobStatus,
    MediaType,
)
from app.infrastructure.database.models.asset import Asset
from app.infrastructure.database.models.defect import Defect
from app.infrastructure.database.models.job import JobFrame, ProcessingJob
from app.infrastructure.database.models.observation import Observation
from sqlalchemy import func, select

from tests.fixtures.helpers import create_queued_job, ingest_image, seed_upload_row
from tests.fixtures.media import make_jpeg_bytes, make_video_file, upload_metadata
from tests.fixtures.ml_stub import StubMLProvider

pytestmark = pytest.mark.integration


async def _run_pipeline(database, storage, settings, job_id, ml=None) -> ProcessingJob:
    pipeline = ProcessingPipeline(database, storage, ml or StubMLProvider(), settings)
    await pipeline.run(job_id)
    async with database.session() as session:
        job = await session.get(ProcessingJob, job_id)
        await session.refresh(job)
        return job


async def _counts(database, job_id):
    async with database.session() as session:
        observations = (
            await session.execute(
                select(func.count(Observation.id)).where(Observation.processing_job_id == job_id)
            )
        ).scalar_one()
        assets = (await session.execute(select(func.count(Asset.id)))).scalar_one()
        defects = (await session.execute(select(func.count(Defect.id)))).scalar_one()
        frames = (
            await session.execute(select(func.count(JobFrame.id)).where(JobFrame.job_id == job_id))
        ).scalar_one()
        return observations, assets, defects, frames


async def test_image_pipeline_creates_asset_observation_defect(database, settings, tmp_path):
    from app.infrastructure.storage.local import LocalFilesystemStorage

    storage = LocalFilesystemStorage(str(tmp_path / "storage"))
    upload = await ingest_image(
        database,
        storage,
        settings,
        jpeg=make_jpeg_bytes(seed=1),
        metadata=upload_metadata(),
    )
    job = await create_queued_job(database, upload.id)
    finished = await _run_pipeline(database, storage, settings, job.id)

    assert finished.status == JobStatus.COMPLETED
    assert finished.progress == 1.0
    assert finished.total_frames == 1
    assert finished.processed_frames == 1
    observations, assets, defects, frames = await _counts(database, job.id)
    assert observations == 1
    assert assets == 1
    assert defects == 1
    assert frames == 1

    async with database.session() as session:
        obs = (await session.execute(select(Observation))).scalar_one()
        assert obs.geolocation_status == GeolocationStatus.CONFIRMED
        assert obs.location is not None
        assert obs.dedup_result == DeduplicationResult.NEW_ASSET
        assert obs.model_name == "stub-detector"
        assert obs.raw_model_payload["object_type"] == "telecom_well"
        assert obs.image_id is not None
        assert obs.crop_image_id is not None
        asset = (await session.execute(select(Asset))).scalar_one()
        assert asset.current_condition == "damaged_cover"
        assert asset.current_severity == 4
        assert asset.current_priority is not None
        assert asset.priority_policy_version == settings.risk_policy_version
        assert asset.priority_factors is not None
        defect = (await session.execute(select(Defect))).scalar_one()
        assert defect.defect_type == "damaged_cover"
        assert defect.asset_id == asset.id


async def test_no_gps_creates_unlocated_observation(database, settings, tmp_path):
    from app.infrastructure.storage.local import LocalFilesystemStorage

    storage = LocalFilesystemStorage(str(tmp_path / "storage"))
    upload = await ingest_image(
        database,
        storage,
        settings,
        jpeg=make_jpeg_bytes(seed=2),
        metadata=upload_metadata(with_gps=False),
    )
    job = await create_queued_job(database, upload.id)
    finished = await _run_pipeline(database, storage, settings, job.id)
    assert finished.status == JobStatus.COMPLETED
    async with database.session() as session:
        obs = (await session.execute(select(Observation))).scalar_one()
        assert obs.geolocation_status == GeolocationStatus.UNAVAILABLE
        assert obs.location is None
        asset = (await session.execute(select(Asset))).scalar_one()
        assert asset.location is None
        assert asset.geolocation_status == GeolocationStatus.UNAVAILABLE


async def test_rerun_is_idempotent(database, settings, tmp_path):
    from app.infrastructure.storage.local import LocalFilesystemStorage

    storage = LocalFilesystemStorage(str(tmp_path / "storage"))
    upload = await ingest_image(
        database,
        storage,
        settings,
        jpeg=make_jpeg_bytes(seed=3),
        metadata=upload_metadata(),
    )
    job = await create_queued_job(database, upload.id)
    await _run_pipeline(database, storage, settings, job.id)
    first = await _counts(database, job.id)
    await _run_pipeline(database, storage, settings, job.id)
    second = await _counts(database, job.id)
    assert first == second


async def test_video_with_rejected_frames(database, settings, tmp_path):
    from app.infrastructure.storage.local import LocalFilesystemStorage

    storage = LocalFilesystemStorage(str(tmp_path / "storage"))
    video_path = str(tmp_path / "survey.mp4")
    make_video_file(video_path, frames=30, fps=10, bad_frame_indices=(10, 11, 12, 13, 14))
    with open(video_path, "rb") as fh:  # noqa: ASYNC230
        content = fh.read()
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
    finished = await _run_pipeline(database, storage, settings, job.id)
    assert finished.status == JobStatus.COMPLETED
    assert finished.total_frames >= 3
    assert finished.rejected_frames >= 1
    async with database.session() as session:
        rejected = (
            (await session.execute(select(JobFrame).where(JobFrame.status == FrameStatus.REJECTED)))
            .scalars()
            .all()
        )
        assert rejected
        assert all(r.reject_reason for r in rejected)


async def test_ml_timeout_marks_frames_failed(database, settings, tmp_path):
    from app.infrastructure.storage.local import LocalFilesystemStorage

    storage = LocalFilesystemStorage(str(tmp_path / "storage"))
    upload = await ingest_image(
        database,
        storage,
        settings,
        jpeg=make_jpeg_bytes(seed=4),
        metadata=upload_metadata(),
    )
    job = await create_queued_job(database, upload.id)
    ml = StubMLProvider(fail_with=MLTimeoutError("model timed out"))
    finished = await _run_pipeline(database, storage, settings, job.id, ml=ml)
    assert finished.status == JobStatus.FAILED
    assert finished.error_code == "all_frames_failed"
    assert finished.failed_frames == 1
    async with database.session() as session:
        frame = (await session.execute(select(JobFrame))).scalar_one()
        assert frame.status == FrameStatus.FAILED
        assert frame.error_code == "ml_timeout"


async def test_corrupted_file_fails_job(database, settings, tmp_path):
    from app.infrastructure.storage.local import LocalFilesystemStorage

    storage = LocalFilesystemStorage(str(tmp_path / "storage"))
    upload = await seed_upload_row(
        database,
        storage,
        key=f"uploads/{uuid.uuid4()}/broken.jpg",
        content=b"this is not an image at all",
        media_type=MediaType.IMAGE,
    )
    job = await create_queued_job(database, upload.id)
    finished = await _run_pipeline(database, storage, settings, job.id)
    assert finished.status == JobStatus.FAILED
    assert finished.error_code == "validation_error"


async def test_storage_failure_fails_job(database, settings, tmp_path):
    from app.infrastructure.storage.local import LocalFilesystemStorage

    storage = LocalFilesystemStorage(str(tmp_path / "storage"))
    upload = await ingest_image(
        database,
        storage,
        settings,
        jpeg=make_jpeg_bytes(seed=5),
        metadata=upload_metadata(),
    )
    job = await create_queued_job(database, upload.id)

    class BrokenStorage:
        async def download_to_file(self, key, path):
            raise StorageError("storage down")

    finished = await _run_pipeline(database, BrokenStorage(), settings, job.id)
    assert finished.status == JobStatus.FAILED
    assert finished.error_code == "storage_unavailable"


async def test_cancelled_job_not_processed(database, settings, tmp_path):
    from app.infrastructure.storage.local import LocalFilesystemStorage

    storage = LocalFilesystemStorage(str(tmp_path / "storage"))
    upload = await ingest_image(
        database,
        storage,
        settings,
        jpeg=make_jpeg_bytes(seed=6),
        metadata=upload_metadata(),
    )
    job = await create_queued_job(database, upload.id)
    async with database.session() as session:
        row = await session.get(ProcessingJob, job.id)
        row.status = JobStatus.CANCELLED
        await session.commit()
    ml = StubMLProvider()
    await _run_pipeline(database, storage, settings, job.id, ml=ml)
    assert ml.calls == 0
    observations, _, _, _ = await _counts(database, job.id)
    assert observations == 0


async def test_real_mock_provider_pipeline(database, settings, tmp_path):
    from app.infrastructure.ml.mock_provider import MockMLProvider
    from app.infrastructure.storage.local import LocalFilesystemStorage

    storage = LocalFilesystemStorage(str(tmp_path / "storage"))
    upload = await ingest_image(
        database,
        storage,
        settings,
        jpeg=make_jpeg_bytes(seed=7),
        metadata=upload_metadata(),
    )
    job = await create_queued_job(database, upload.id)
    finished = await _run_pipeline(database, storage, settings, job.id, ml=MockMLProvider())
    assert finished.status == JobStatus.COMPLETED
    async with database.session() as session:
        observations = (
            (
                await session.execute(
                    select(Observation).where(Observation.processing_job_id == job.id)
                )
            )
            .scalars()
            .all()
        )
        for obs in observations:
            assert obs.model_name == "mock-infrastructure-detector"
            assert 0 <= obs.detector_confidence <= 1
            assert obs.dedup_result is not None
