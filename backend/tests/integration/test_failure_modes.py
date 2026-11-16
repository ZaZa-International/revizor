"""Stage-4 failure-mode integration tests: degraded infrastructure and bad input.

Queue outage compensation (REL-7), Redis-down login fallback (SEC-15),
S3-down upload envelope, PG-down readiness, corrupted video, upload size
limit, ML unavailability and stale-PROCESSING recovery through the real API
(REL-1). All stubs are installed on app.state and restored by monkeypatch.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
from app.application.use_cases.processing.pipeline import ProcessingPipeline
from app.config import Settings
from app.core.exceptions import MLUnavailableError, StorageError
from app.domain.enums import FrameStatus, JobStatus, MediaType
from app.infrastructure.database.models.job import JobFrame, ProcessingJob
from app.infrastructure.database.session import Database
from app.infrastructure.storage.local import LocalFilesystemStorage
from fastapi import FastAPI
from redis.exceptions import RedisError
from sqlalchemy import select, text

from tests.api.test_assets_api import seed_job, seed_upload, seed_upload_with_file
from tests.fixtures.helpers import create_queued_job, ingest_image, seed_upload_row
from tests.fixtures.media import make_jpeg_bytes, upload_metadata
from tests.fixtures.ml_stub import StubMLProvider

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def _ensure_database_setup(database: Database) -> None:
    """Pull the session-scoped database into the fixture closure so it is set
    up before clean_tables resolves it dynamically inside a running loop."""


async def _fail_enqueue(job_id: uuid.UUID) -> str | None:
    raise RuntimeError("simulated queue outage")


async def test_queue_down_create_job_compensates_to_failed(
    client: httpx.AsyncClient,
    app: FastAPI,
    admin_headers: dict,
    database: Database,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    upload_id = await seed_upload(database)
    monkeypatch.setattr(app.state.queue, "enqueue_processing", _fail_enqueue)
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as tolerant:
        response = await tolerant.post(
            "/api/v1/jobs", headers=admin_headers, json={"upload_id": str(upload_id)}
        )
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "internal_error"
    listing = await client.get(
        "/api/v1/jobs", headers=admin_headers, params={"upload_id": str(upload_id)}
    )
    assert listing.status_code == 200
    assert listing.json()["total"] == 1
    job = listing.json()["items"][0]
    assert job["status"] == "FAILED"
    assert job["error_code"] == "queue_unavailable"
    assert job["finished_at"] is not None


async def test_queue_down_retry_compensates_to_failed(
    client: httpx.AsyncClient,
    app: FastAPI,
    admin_headers: dict,
    database: Database,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    upload_id = await seed_upload_with_file(database, settings.storage_local_path, seed=801)
    seeded = await seed_job(database, upload_id=upload_id, status=JobStatus.FAILED)
    monkeypatch.setattr(app.state.queue, "enqueue_processing", _fail_enqueue)
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as tolerant:
        response = await tolerant.post(f"/api/v1/jobs/{seeded.job_id}/retry", headers=admin_headers)
    assert response.status_code == 500
    job = await client.get(f"/api/v1/jobs/{seeded.job_id}", headers=admin_headers)
    assert job.status_code == 200
    body = job.json()
    assert body["status"] == "FAILED"
    assert body["error_code"] == "queue_unavailable"
    assert body["finished_at"] is not None


class _RedisDown:
    def pipeline(self) -> None:
        raise RedisError("simulated redis outage")


async def test_redis_down_login_still_works(
    client: httpx.AsyncClient, app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(app.state, "redis", _RedisDown())
    response = await client.post(
        "/api/v1/auth/login", json={"username": "admin", "password": "admin-test-password"}
    )
    assert response.status_code == 200, response.text
    assert response.json()["access_token"]


class _StorageDown:
    async def upload_file(self, key: str, path: str, content_type: str) -> None:
        raise StorageError("simulated S3 outage")


async def test_storage_down_upload_returns_503_envelope(
    client: httpx.AsyncClient,
    app: FastAPI,
    admin_headers: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(app.state, "storage", _StorageDown())
    response = await client.post(
        "/api/v1/uploads",
        headers=admin_headers,
        files={"file": ("frame.jpg", make_jpeg_bytes(seed=802), "image/jpeg")},
    )
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "storage_unavailable"
    listing = await client.get("/api/v1/uploads", headers=admin_headers)
    assert listing.json()["total"] == 0


class _DatabaseDown:
    def session(self) -> None:
        raise RuntimeError("simulated postgres outage")


async def test_pg_down_readiness_returns_503(
    client: httpx.AsyncClient, app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(app.state, "database", _DatabaseDown())
    response = await client.get("/health/ready")
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "not_ready"
    assert body["components"]["database"]["status"] == "error"


async def test_corrupted_video_fails_job_with_validation_error(
    client: httpx.AsyncClient, app: FastAPI, admin_headers: dict, database: Database
) -> None:
    upload = await seed_upload_row(
        database,
        app.state.storage,
        key=f"uploads/{uuid.uuid4()}/broken.mp4",
        content=b"not a video",
        media_type=MediaType.VIDEO,
    )
    response = await client.post(
        "/api/v1/jobs", headers=admin_headers, json={"upload_id": str(upload.id)}
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "FAILED"
    assert body["error_code"] == "validation_error"
    frames = await client.get(f"/api/v1/jobs/{body['id']}/frames", headers=admin_headers)
    assert frames.json()["total"] == 0


async def test_upload_over_configured_max_size_422(
    client: httpx.AsyncClient,
    admin_headers: dict,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "max_upload_size_bytes", 1024)
    data = make_jpeg_bytes(seed=803)
    assert len(data) > 1024
    response = await client.post(
        "/api/v1/uploads",
        headers=admin_headers,
        files={"file": ("frame.jpg", data, "image/jpeg")},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


async def test_ml_unavailable_marks_frames_and_job_failed(
    database: Database, settings: Settings, tmp_path: Path
) -> None:
    storage = LocalFilesystemStorage(str(tmp_path / "storage"))
    upload = await ingest_image(
        database, storage, settings, jpeg=make_jpeg_bytes(seed=804), metadata=upload_metadata()
    )
    job = await create_queued_job(database, upload.id)
    ml = StubMLProvider(fail_with=MLUnavailableError("simulated ML outage"))
    pipeline = ProcessingPipeline(database, storage, ml, settings)
    await pipeline.run(job.id)

    async with database.session() as session:
        finished = await session.get(ProcessingJob, job.id)
        assert finished is not None
        assert finished.status == JobStatus.FAILED
        assert finished.error_code == "all_frames_failed"
        assert finished.failed_frames == 1
        frame = (
            await session.execute(select(JobFrame).where(JobFrame.job_id == job.id))
        ).scalar_one()
        assert frame.status == FrameStatus.FAILED
        assert frame.error_code == "ml_unavailable"


async def _age_job(database: Database, job_id: uuid.UUID, *, age_seconds: int) -> None:
    async with database.session() as session:
        await session.execute(
            text(
                "UPDATE processing_jobs SET status = 'PROCESSING', updated_at = :ts WHERE id = :id"
            ),
            {"ts": datetime.now(UTC) - timedelta(seconds=age_seconds), "id": str(job_id)},
        )
        await session.commit()


async def test_stale_processing_retry_via_api_recovers(
    client: httpx.AsyncClient, admin_headers: dict, database: Database, settings: Settings
) -> None:
    upload_id = await seed_upload_with_file(database, settings.storage_local_path, seed=805)
    stale = await create_queued_job(database, upload_id)
    await _age_job(database, stale.id, age_seconds=7200)
    response = await client.post(f"/api/v1/jobs/{stale.id}/retry", headers=admin_headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] in {"QUEUED", "COMPLETED"}
    assert body["status"] == "COMPLETED"
    assert body["processed_frames"] >= 1
    assert body["error_code"] is None


async def test_fresh_processing_retry_via_api_rejected(
    client: httpx.AsyncClient, admin_headers: dict, database: Database, settings: Settings
) -> None:
    upload_id = await seed_upload_with_file(database, settings.storage_local_path, seed=806)
    fresh = await create_queued_job(database, upload_id)
    await _age_job(database, fresh.id, age_seconds=1)
    response = await client.post(f"/api/v1/jobs/{fresh.id}/retry", headers=admin_headers)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "invalid_job_state"
