"""Stage-4 concurrency regression tests against real PostgreSQL/Redis.

Optimistic-lock PATCH race, active-upload job guard under concurrent creates,
idempotent review replay under a same-key race, append-only reviews with
different keys, and cross-upload deduplication under concurrent pipelines
(advisory grid-cell lock).
"""

from __future__ import annotations

import asyncio
import uuid
from pathlib import Path

import httpx
import pytest
from app.application.use_cases.processing.pipeline import ProcessingPipeline
from app.config import Settings
from app.domain.enums import DeduplicationResult, JobStatus
from app.infrastructure.database.models.asset import Asset
from app.infrastructure.database.models.job import ProcessingJob
from app.infrastructure.database.models.observation import Observation
from app.infrastructure.database.models.review import Review
from app.infrastructure.database.session import Database
from app.infrastructure.storage.local import LocalFilesystemStorage
from fastapi import FastAPI
from sqlalchemy import func, select

from tests.api.test_assets_api import seed_asset, seed_observation_chain, seed_upload
from tests.fixtures.helpers import create_queued_job, ingest_image
from tests.fixtures.media import make_jpeg_bytes, upload_metadata
from tests.fixtures.ml_stub import StubMLProvider

pytestmark = pytest.mark.integration

_TRAINING_UPSERT_BUG = (
    "BUG: ReviewService._upsert_training_example is a read-then-insert upsert "
    "(app/application/services/reviews.py:243-256); two concurrent reviews of the "
    "same observation both see no existing row and both INSERT, violating "
    "uq_training_examples_observation_id -> one request gets 409 conflict instead "
    "of succeeding. Expected: concurrent reviews never fail on this constraint."
)

_IDEMPOTENCY_RACE_BUG = (
    "BUG: concurrent same-Idempotency-Key POST /reviews does not replay: the loser "
    "gets 409 (training-example upsert race, app/application/services/reviews.py:243-256) "
    "and the idempotency layer swallows the unique violation without re-fetching the "
    "cached response (app/application/services/idempotency.py:45-46, "
    "app/api/v1/idempotency.py:38-50). Expected: both requests return 201 with the "
    "same review id and exactly one review row."
)


@pytest.fixture(autouse=True)
def _ensure_database_setup(database: Database) -> None:
    """Pull the session-scoped database into the fixture closure so it is set
    up before clean_tables resolves it dynamically inside a running loop."""


async def test_concurrent_patch_same_expected_version_one_wins(
    client: httpx.AsyncClient, admin_headers: dict, database: Database
) -> None:
    asset_id = await seed_asset(database)

    async def patch(name: str) -> httpx.Response:
        return await client.patch(
            f"/api/v1/assets/{asset_id}",
            headers=admin_headers,
            json={"display_name": name, "expected_version": 1},
        )

    first, second = await asyncio.gather(patch("writer-a"), patch("writer-b"))
    assert sorted([first.status_code, second.status_code]) == [200, 409]
    loser = first if first.status_code == 409 else second
    assert loser.json()["error"]["code"] == "conflict"
    winner = first if first.status_code == 200 else second
    assert winner.json()["version"] == 2

    current = await client.get(f"/api/v1/assets/{asset_id}", headers=admin_headers)
    assert current.json()["version"] == 2
    assert current.json()["display_name"] == winner.json()["display_name"]


async def test_concurrent_jobs_same_upload_active_guard(
    client: httpx.AsyncClient,
    app: FastAPI,
    admin_headers: dict,
    database: Database,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    upload_id = await seed_upload(database)

    async def noop_enqueue(job_id: uuid.UUID) -> str | None:
        return f"noop:{job_id}"

    monkeypatch.setattr(app.state.queue, "enqueue_processing", noop_enqueue)

    async def create(key: str) -> httpx.Response:
        return await client.post(
            "/api/v1/jobs",
            headers={**admin_headers, "Idempotency-Key": key},
            json={"upload_id": str(upload_id)},
        )

    first, second = await asyncio.gather(create(str(uuid.uuid4())), create(str(uuid.uuid4())))
    assert sorted([first.status_code, second.status_code]) == [201, 409]
    loser = first if first.status_code == 409 else second
    assert loser.json()["error"]["code"] == "invalid_job_state"
    listing = await client.get(
        "/api/v1/jobs", headers=admin_headers, params={"upload_id": str(upload_id)}
    )
    assert listing.json()["total"] == 1


async def test_concurrent_reviews_same_idempotency_key_single_review(
    client: httpx.AsyncClient, admin_headers: dict, database: Database
) -> None:
    chain = await seed_observation_chain(database)
    body = {"observation_id": str(chain.observation_id), "decision": "CONFIRMED"}
    headers = {**admin_headers, "Idempotency-Key": str(uuid.uuid4())}

    async def review() -> httpx.Response:
        return await client.post("/api/v1/reviews", headers=headers, json=body)

    first, second = await asyncio.gather(review(), review())
    assert first.status_code == 201, first.text
    assert second.status_code == 201, second.text
    assert first.json()["id"] == second.json()["id"]
    async with database.session() as session:
        count = (
            await session.execute(
                select(func.count(Review.id)).where(Review.observation_id == chain.observation_id)
            )
        ).scalar_one()
    assert count == 1


async def test_concurrent_reviews_different_keys_append_only(
    client: httpx.AsyncClient, admin_headers: dict, database: Database
) -> None:
    chain = await seed_observation_chain(database)
    body = {"observation_id": str(chain.observation_id), "decision": "CONFIRMED"}

    async def review(key: str) -> httpx.Response:
        return await client.post(
            "/api/v1/reviews", headers={**admin_headers, "Idempotency-Key": key}, json=body
        )

    first, second = await asyncio.gather(review(str(uuid.uuid4())), review(str(uuid.uuid4())))
    assert first.status_code == 201, first.text
    assert second.status_code == 201, second.text
    assert first.json()["id"] != second.json()["id"]
    async with database.session() as session:
        count = (
            await session.execute(
                select(func.count(Review.id)).where(Review.observation_id == chain.observation_id)
            )
        ).scalar_one()
    assert count == 2


async def test_concurrent_rejected_reviews_different_keys_append_only(
    client: httpx.AsyncClient, admin_headers: dict, database: Database
) -> None:
    chain = await seed_observation_chain(database)
    body = {"observation_id": str(chain.observation_id), "decision": "REJECTED"}

    async def review(key: str) -> httpx.Response:
        return await client.post(
            "/api/v1/reviews", headers={**admin_headers, "Idempotency-Key": key}, json=body
        )

    first, second = await asyncio.gather(review(str(uuid.uuid4())), review(str(uuid.uuid4())))
    assert first.status_code == 201, first.text
    assert second.status_code == 201, second.text
    assert first.json()["id"] != second.json()["id"]
    async with database.session() as session:
        count = (
            await session.execute(
                select(func.count(Review.id)).where(Review.observation_id == chain.observation_id)
            )
        ).scalar_one()
    assert count == 2


async def test_concurrent_pipelines_same_area_single_asset(
    database: Database, settings: Settings, tmp_path: Path
) -> None:
    storage = LocalFilesystemStorage(str(tmp_path / "storage"))
    metadata = upload_metadata()
    upload_a = await ingest_image(
        database, storage, settings, jpeg=make_jpeg_bytes(seed=810), metadata=metadata
    )
    upload_b = await ingest_image(
        database, storage, settings, jpeg=make_jpeg_bytes(seed=811), metadata=metadata
    )
    job_a = await create_queued_job(database, upload_a.id)
    job_b = await create_queued_job(database, upload_b.id)
    pipeline_a = ProcessingPipeline(database, storage, StubMLProvider(), settings)
    pipeline_b = ProcessingPipeline(database, storage, StubMLProvider(), settings)
    await asyncio.gather(pipeline_a.run(job_a.id), pipeline_b.run(job_b.id))

    async with database.session() as session:
        for job_id in (job_a.id, job_b.id):
            job = await session.get(ProcessingJob, job_id)
            assert job is not None
            assert job.status == JobStatus.COMPLETED
        assets = int((await session.execute(select(func.count(Asset.id)))).scalar_one())
        assert assets == 1
        observations = (await session.execute(select(Observation))).scalars().all()
        assert len(observations) == 2
        assert {obs.dedup_result for obs in observations} == {
            DeduplicationResult.NEW_ASSET,
            DeduplicationResult.MATCHED,
        }
        assert len({obs.asset_id for obs in observations}) == 1
