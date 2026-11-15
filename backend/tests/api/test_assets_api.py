"""Assets API: filters, optimistic-lock patch, geolocation, subresources, nearby.

Also hosts shared DB seeding helpers reused by other API/contract test modules.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from app.domain.enums import (
    DefectStatus,
    FrameStatus,
    GeolocationSource,
    GeolocationStatus,
    JobStatus,
    LifecycleStatus,
    MediaType,
    ObservationReviewStatus,
    PriorityBand,
    StorageObjectKind,
)
from app.infrastructure.database.models.asset import Asset
from app.infrastructure.database.models.defect import Defect, defect_observations
from app.infrastructure.database.models.job import JobFrame, ProcessingJob
from app.infrastructure.database.models.observation import Observation
from app.infrastructure.database.models.stored_file import StoredFile
from app.infrastructure.database.models.upload import Upload
from geoalchemy2 import WKTElement

from tests.fixtures.media import make_jpeg_bytes, upload_metadata

pytestmark = pytest.mark.api


def point(lon: float, lat: float) -> WKTElement:
    return WKTElement(f"POINT({lon} {lat})", srid=4326)


def _random_checksum() -> str:
    return hashlib.sha256(uuid.uuid4().bytes).hexdigest()


def _naive_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


async def seed_asset(
    database,
    *,
    asset_type: str = "telecom_well",
    lon: float | None = None,
    lat: float | None = None,
    display_name: str | None = None,
    external_id: str | None = None,
    priority_band: PriorityBand | None = None,
    current_severity: int | None = None,
    current_condition: str | None = None,
) -> uuid.UUID:
    located = lon is not None and lat is not None
    async with database.session() as session:
        asset = Asset(
            asset_type=asset_type,
            display_name=display_name,
            external_id=external_id,
            location=point(lon, lat) if located else None,
            geolocation_status=(
                GeolocationStatus.CONFIRMED if located else GeolocationStatus.UNAVAILABLE
            ),
            priority_band=priority_band,
            current_severity=current_severity,
            current_condition=current_condition,
            lifecycle_status=LifecycleStatus.ACTIVE,
            version=1,
        )
        session.add(asset)
        await session.commit()
        return asset.id


async def seed_upload(database) -> uuid.UUID:
    async with database.session() as session:
        upload = Upload(
            original_filename="seed.jpg",
            storage_key=f"uploads/{uuid.uuid4()}/seed.jpg",
            content_type="image/jpeg",
            file_size=128,
            checksum_sha256=_random_checksum(),
            media_type=MediaType.IMAGE,
            metadata_={},
        )
        session.add(upload)
        await session.commit()
        return upload.id


async def seed_upload_with_file(
    database,
    storage_root: str,
    *,
    metadata: dict | None = None,
    seed: int = 99,
) -> uuid.UUID:
    data = make_jpeg_bytes(seed=seed)
    upload_id = uuid.uuid4()
    storage_key = f"uploads/{upload_id}/seed.jpg"
    path = Path(storage_root) / storage_key
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    async with database.session() as session:
        upload = Upload(
            id=upload_id,
            original_filename="seed.jpg",
            storage_key=storage_key,
            content_type="image/jpeg",
            file_size=len(data),
            checksum_sha256=hashlib.sha256(data).hexdigest(),
            media_type=MediaType.IMAGE,
            metadata_=metadata or {},
        )
        session.add(upload)
        await session.commit()
        return upload_id


async def seed_job(
    database,
    *,
    upload_id: uuid.UUID | None = None,
    status: JobStatus = JobStatus.COMPLETED,
    frames: int = 0,
) -> SimpleNamespace:
    if upload_id is None:
        upload_id = await seed_upload(database)
    async with database.session() as session:
        job = ProcessingJob(
            upload_id=upload_id,
            status=status,
            progress=1.0 if status == JobStatus.COMPLETED else 0.0,
            total_frames=frames,
            processed_frames=frames,
            options={},
        )
        session.add(job)
        await session.flush()
        for index in range(frames):
            session.add(
                JobFrame(
                    job_id=job.id,
                    frame_index=index,
                    status=FrameStatus.PROCESSED,
                    observed_at=_naive_now(),
                )
            )
        await session.commit()
        return SimpleNamespace(job_id=job.id, upload_id=upload_id)


async def seed_observation_chain(
    database,
    *,
    with_asset: bool = True,
    with_image: bool = True,
    with_defect: bool = False,
    asset_type: str = "telecom_well",
    condition: str = "damaged_cover",
    severity: int = 4,
    lon: float | None = None,
    lat: float | None = None,
) -> SimpleNamespace:
    """Minimal Upload -> ProcessingJob -> StoredFile -> Asset -> Observation rows."""
    now = _naive_now()
    located = lon is not None and lat is not None
    async with database.session() as session:
        upload = Upload(
            original_filename="chain.jpg",
            storage_key=f"uploads/{uuid.uuid4()}/chain.jpg",
            content_type="image/jpeg",
            file_size=128,
            checksum_sha256=_random_checksum(),
            media_type=MediaType.IMAGE,
            metadata_={},
        )
        session.add(upload)
        await session.flush()
        job = ProcessingJob(
            upload_id=upload.id,
            status=JobStatus.COMPLETED,
            progress=1.0,
            total_frames=1,
            processed_frames=1,
            options={},
        )
        session.add(job)
        await session.flush()
        stored = None
        if with_image:
            stored = StoredFile(
                storage_key=f"frames/{job.id}/000000.jpg",
                kind=StorageObjectKind.FRAME,
                upload_id=upload.id,
                content_type="image/jpeg",
                file_size=128,
                width=640,
                height=480,
            )
            session.add(stored)
            await session.flush()
        asset = None
        if with_asset:
            asset = Asset(
                asset_type=asset_type,
                location=point(lon, lat) if located else None,
                geolocation_status=(
                    GeolocationStatus.CONFIRMED if located else GeolocationStatus.UNAVAILABLE
                ),
                current_condition=condition,
                current_severity=severity,
                first_observed_at=now,
                last_observed_at=now,
                version=1,
            )
            session.add(asset)
            await session.flush()
        observation = Observation(
            asset_id=asset.id if asset else None,
            processing_job_id=job.id,
            frame_id="frame_000000",
            observed_at=now,
            detected_at=now,
            object_type=asset_type,
            condition_class=condition,
            detector_confidence=0.9,
            severity=severity,
            bbox={"x_min": 10.0, "y_min": 10.0, "x_max": 100.0, "y_max": 100.0},
            image_width=640,
            image_height=480,
            image_id=stored.id if stored else None,
            location=point(lon, lat) if located else None,
            geolocation_status=(
                GeolocationStatus.CONFIRMED if located else GeolocationStatus.UNAVAILABLE
            ),
            geolocation_source=GeolocationSource.GPS if located else GeolocationSource.UNKNOWN,
            review_status=ObservationReviewStatus.UNREVIEWED,
            effective_asset_type=asset_type,
            effective_condition=condition,
            effective_severity=severity,
        )
        session.add(observation)
        await session.flush()
        defect = None
        if with_defect:
            assert asset is not None
            defect = Defect(
                asset_id=asset.id,
                defect_type=condition,
                severity=severity,
                status=DefectStatus.OPEN,
                first_detected_at=now,
                last_detected_at=now,
            )
            session.add(defect)
            await session.flush()
            await session.execute(
                defect_observations.insert().values(
                    defect_id=defect.id, observation_id=observation.id
                )
            )
        await session.commit()
        return SimpleNamespace(
            upload_id=upload.id,
            job_id=job.id,
            image_id=stored.id if stored else None,
            image_storage_key=stored.storage_key if stored else None,
            asset_id=asset.id if asset else None,
            observation_id=observation.id,
            defect_id=defect.id if defect else None,
        )


async def test_assets_envelope_after_pipeline_upload(client, admin_headers, database, settings):
    upload_id = await seed_upload_with_file(
        database, settings.storage_local_path, metadata=upload_metadata()
    )
    job = await client.post(
        "/api/v1/jobs", headers=admin_headers, json={"upload_id": str(upload_id)}
    )
    assert job.status_code == 201, job.text
    response = await client.get("/api/v1/assets", headers=admin_headers)
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"items", "total", "page", "page_size", "pages"}
    assert isinstance(body["items"], list)
    assert body["total"] >= 0


async def test_filter_asset_type(client, admin_headers, database):
    await seed_asset(database, asset_type="telecom_well")
    pole_id = await seed_asset(database, asset_type="pole")
    response = await client.get(
        "/api/v1/assets", headers=admin_headers, params={"asset_type": "pole"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["id"] == str(pole_id)
    assert body["items"][0]["asset_type"] == "pole"


async def test_filter_priority_band(client, admin_headers, database):
    await seed_asset(database, priority_band=PriorityBand.LOW_PRIORITY)
    high_id = await seed_asset(database, priority_band=PriorityBand.HIGH_PRIORITY)
    response = await client.get(
        "/api/v1/assets",
        headers=admin_headers,
        params={"priority_band": "HIGH_PRIORITY"},
    )
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["id"] == str(high_id)
    assert body["items"][0]["priority_band"] == "HIGH_PRIORITY"


async def test_filter_bbox_valid(client, admin_headers, database):
    inside_id = await seed_asset(database, lon=37.6173, lat=55.7558)
    await seed_asset(database, lon=37.95, lat=55.95)
    response = await client.get(
        "/api/v1/assets",
        headers=admin_headers,
        params={"bbox": "37.6,55.7,37.7,55.8"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["id"] == str(inside_id)


@pytest.mark.parametrize(
    "bbox",
    ["37.7,55.8,37.6,55.7", "not-a-bbox", "200,55.7,201,55.8", "37.6,55.7,37.7"],
)
async def test_filter_bbox_invalid_422(client, admin_headers, bbox):
    response = await client.get("/api/v1/assets", headers=admin_headers, params={"bbox": bbox})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


async def test_search_by_display_name(client, admin_headers, database):
    target_id = await seed_asset(database, display_name="Well-Alpha-42")
    await seed_asset(database, display_name="Pole-Beta-7")
    response = await client.get("/api/v1/assets", headers=admin_headers, params={"search": "Alpha"})
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["id"] == str(target_id)


async def test_get_unknown_asset_404(client, admin_headers):
    response = await client.get(f"/api/v1/assets/{uuid.uuid4()}", headers=admin_headers)
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


async def test_patch_display_name(client, admin_headers, database):
    asset_id = await seed_asset(database)
    response = await client.patch(
        f"/api/v1/assets/{asset_id}",
        headers=admin_headers,
        json={"display_name": "Renamed well"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["display_name"] == "Renamed well"
    assert body["version"] == 2


async def test_patch_priority_override_without_reason_422(client, admin_headers, database):
    asset_id = await seed_asset(database)
    response = await client.patch(
        f"/api/v1/assets/{asset_id}",
        headers=admin_headers,
        json={"priority_override": 90},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


async def test_patch_wrong_expected_version_409(client, admin_headers, database):
    asset_id = await seed_asset(database)
    response = await client.patch(
        f"/api/v1/assets/{asset_id}",
        headers=admin_headers,
        json={"display_name": "Conflict", "expected_version": 999},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "conflict"


async def test_patch_location_sets_confirmed(client, admin_headers, database):
    asset_id = await seed_asset(database)
    response = await client.patch(
        f"/api/v1/assets/{asset_id}",
        headers=admin_headers,
        json={"location": {"longitude": 37.6173, "latitude": 55.7558}},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["geolocation_status"] == "CONFIRMED"
    assert body["longitude"] == pytest.approx(37.6173)
    assert body["latitude"] == pytest.approx(55.7558)


async def test_subresources_history_observations_defects(client, admin_headers, database):
    chain = await seed_observation_chain(database, with_defect=True)
    history = await client.get(f"/api/v1/assets/{chain.asset_id}/history", headers=admin_headers)
    assert history.status_code == 200
    assert isinstance(history.json(), list)

    observations = await client.get(
        f"/api/v1/assets/{chain.asset_id}/observations", headers=admin_headers
    )
    assert observations.status_code == 200
    obs_body = observations.json()
    assert set(obs_body) == {"items", "total", "page", "page_size", "pages"}
    assert obs_body["total"] == 1
    assert obs_body["items"][0]["id"] == str(chain.observation_id)

    defects = await client.get(f"/api/v1/assets/{chain.asset_id}/defects", headers=admin_headers)
    assert defects.status_code == 200
    defect_body = defects.json()
    assert defect_body["total"] == 1
    assert defect_body["items"][0]["id"] == str(chain.defect_id)
    assert defect_body["items"][0]["observation_count"] == 1


async def test_nearby_returns_distance_sorted(client, admin_headers, database):
    near_id = await seed_asset(database, lon=37.6173, lat=55.7558)
    close_id = await seed_asset(database, lon=37.6180, lat=55.7560)
    await seed_asset(database, lon=37.95, lat=55.95)
    response = await client.get(
        "/api/v1/assets/nearby",
        headers=admin_headers,
        params={"longitude": 37.6173, "latitude": 55.7558, "radius_m": 1000},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] == len(body["items"]) == 2
    ids = [item["id"] for item in body["items"]]
    assert ids == [str(near_id), str(close_id)]
    distances = [item["distance_m"] for item in body["items"]]
    assert all(isinstance(d, float) and 0 <= d <= 1000 for d in distances)
    assert distances == sorted(distances)
    assert distances[0] == pytest.approx(0.0, abs=1.0)


async def test_nearby_longitude_out_of_range_422(client, admin_headers):
    response = await client.get(
        "/api/v1/assets/nearby",
        headers=admin_headers,
        params={"longitude": 200, "latitude": 55.7558, "radius_m": 1000},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
