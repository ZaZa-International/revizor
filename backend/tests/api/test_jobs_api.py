"""Jobs API: inline pipeline lifecycle, frames, retry/cancel guards, idempotency."""

from __future__ import annotations

import uuid

import pytest
from app.domain.enums import JobStatus

from tests.api.test_assets_api import seed_job, seed_upload, seed_upload_with_file

pytestmark = pytest.mark.api

_INLINE_PIPELINE_BUG = (
    "BUG: JobService.create_job never commits before InlineJobQueue.enqueue_processing "
    "(app/application/services/jobs.py:57) so the pipeline's separate connection cannot "
    "see the job row (pipeline_job_missing) and it stays QUEUED; additionally pipeline "
    "persistence binds aware datetimes to timezone-naive ORM columns "
    "(app/infrastructure/database/models/observation.py:79-80) which asyncpg rejects"
)


async def test_create_job_inline_pipeline_completes(client, admin_headers, database, settings):
    upload_id = await seed_upload_with_file(database, settings.storage_local_path, seed=31)
    response = await client.post(
        "/api/v1/jobs", headers=admin_headers, json={"upload_id": str(upload_id)}
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["upload_id"] == str(upload_id)
    assert body["status"] == "COMPLETED"
    assert body["progress"] == 1.0
    assert body["total_frames"] >= 1
    assert body["finished_at"] is not None


async def test_get_job(client, admin_headers, database):
    upload_id = await seed_upload(database)
    created = await client.post(
        "/api/v1/jobs", headers=admin_headers, json={"upload_id": str(upload_id)}
    )
    assert created.status_code == 201, created.text
    job_id = created.json()["id"]
    response = await client.get(f"/api/v1/jobs/{job_id}", headers=admin_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == job_id
    assert body["upload_id"] == str(upload_id)
    assert body["status"] in {status.value for status in JobStatus}
    assert isinstance(body["progress"], float)


async def test_job_frames_lists_records(client, admin_headers, database):
    seeded = await seed_job(database, status=JobStatus.COMPLETED, frames=2)
    response = await client.get(f"/api/v1/jobs/{seeded.job_id}/frames", headers=admin_headers)
    assert response.status_code == 200
    frames = response.json()
    assert isinstance(frames, list)
    assert len(frames) == 2
    assert [frame["frame_index"] for frame in frames] == [0, 1]
    assert all(frame["status"] == "PROCESSED" for frame in frames)


async def test_inline_pipeline_produces_frame_records(client, admin_headers, database, settings):
    upload_id = await seed_upload_with_file(database, settings.storage_local_path, seed=33)
    created = await client.post(
        "/api/v1/jobs", headers=admin_headers, json={"upload_id": str(upload_id)}
    )
    assert created.status_code == 201
    response = await client.get(
        f"/api/v1/jobs/{created.json()['id']}/frames", headers=admin_headers
    )
    assert response.status_code == 200
    frames = response.json()
    assert len(frames) >= 1
    assert frames[0]["frame_index"] == 0


async def test_create_job_unknown_upload_404(client, admin_headers):
    response = await client.post(
        "/api/v1/jobs", headers=admin_headers, json={"upload_id": str(uuid.uuid4())}
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


async def test_retry_completed_job_409(client, admin_headers, database):
    seeded = await seed_job(database, status=JobStatus.COMPLETED)
    response = await client.post(f"/api/v1/jobs/{seeded.job_id}/retry", headers=admin_headers)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "invalid_job_state"


async def test_cancel_completed_job_409(client, admin_headers, database):
    seeded = await seed_job(database, status=JobStatus.COMPLETED)
    response = await client.post(f"/api/v1/jobs/{seeded.job_id}/cancel", headers=admin_headers)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "invalid_job_state"


async def test_idempotency_key_returns_same_job(client, admin_headers, database):
    upload_id = await seed_upload(database)
    key = str(uuid.uuid4())
    headers = {**admin_headers, "Idempotency-Key": key}
    first = await client.post("/api/v1/jobs", headers=headers, json={"upload_id": str(upload_id)})
    assert first.status_code == 201, first.text
    second = await client.post("/api/v1/jobs", headers=headers, json={"upload_id": str(upload_id)})
    assert second.status_code in (200, 201)
    assert second.json()["id"] == first.json()["id"]
    listing = await client.get("/api/v1/jobs", headers=admin_headers)
    assert listing.json()["total"] == 1


async def test_list_jobs_filter_status(client, admin_headers, database):
    await seed_job(database, status=JobStatus.COMPLETED)
    await seed_job(database, status=JobStatus.FAILED)
    completed = await client.get(
        "/api/v1/jobs", headers=admin_headers, params={"status": "COMPLETED"}
    )
    assert completed.status_code == 200
    body = completed.json()
    assert body["total"] == 1
    assert body["items"][0]["status"] == "COMPLETED"
    failed = await client.get("/api/v1/jobs", headers=admin_headers, params={"status": "FAILED"})
    assert failed.json()["total"] == 1
    assert failed.json()["items"][0]["status"] == "FAILED"
