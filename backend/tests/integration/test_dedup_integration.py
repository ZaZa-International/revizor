"""Deduplication across surveys against real PostGIS."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from app.application.services.deduplication import DeduplicationService
from app.domain.enums import DeduplicationResult, GeolocationStatus, LifecycleStatus
from app.domain.geospatial.models import GeoPoint
from app.infrastructure.database.models.asset import Asset
from app.infrastructure.database.models.job import ProcessingJob
from app.infrastructure.database.models.upload import Upload
from geoalchemy2 import WKTElement

pytestmark = pytest.mark.integration

POINT = GeoPoint(37.6173, 55.7558)


async def _seed_asset(database, *, lon, lat, asset_type="telecom_well", last_observed=None):
    async with database.session() as session:
        asset = Asset(
            asset_type=asset_type,
            location=WKTElement(f"POINT({lon} {lat})", srid=4326),
            geolocation_status=GeolocationStatus.CONFIRMED,
            lifecycle_status=LifecycleStatus.ACTIVE,
            last_observed_at=last_observed or datetime(2026, 11, 15, 12, 0, 0, tzinfo=UTC),
        )
        session.add(asset)
        await session.commit()
        return asset.id


async def _seed_job(database) -> uuid.UUID:
    async with database.session() as session:
        upload = Upload(
            original_filename="x.jpg",
            storage_key=f"uploads/{uuid.uuid4()}/x.jpg",
            content_type="image/jpeg",
            file_size=1,
            checksum_sha256=uuid.uuid4().hex + uuid.uuid4().hex,
            media_type="IMAGE",
            metadata_={},
        )
        session.add(upload)
        await session.flush()
        job = ProcessingJob(upload_id=upload.id, status="COMPLETED")
        session.add(job)
        await session.commit()
        return job.id


async def test_same_object_resurveyed_matches(database, settings):
    asset_id = await _seed_asset(database, lon=37.6173, lat=55.7558)
    job_id = await _seed_job(database)
    async with database.session() as session:
        service = DeduplicationService(session, settings)
        decision = await service.match(
            object_type="telecom_well",
            point=GeoPoint(37.61732, 55.75581),
            observed_at=datetime(2026, 11, 16, 12, 0, 0, tzinfo=UTC),
            job_id=job_id,
            route_id=None,
            tracking_id=None,
        )
    assert decision.result == DeduplicationResult.MATCHED
    assert decision.asset_id == str(asset_id)
    assert decision.explanation["best_factors"]["spatial"] > 0.8


async def test_different_type_same_place_not_matched(database, settings):
    await _seed_asset(database, lon=37.6173, lat=55.7558, asset_type="pole")
    job_id = await _seed_job(database)
    async with database.session() as session:
        decision = await DeduplicationService(session, settings).match(
            object_type="telecom_well",
            point=POINT,
            observed_at=datetime(2026, 11, 16, 12, 0, 0, tzinfo=UTC),
            job_id=job_id,
            route_id=None,
            tracking_id=None,
        )
    assert decision.result == DeduplicationResult.NEW_ASSET


async def test_far_object_not_matched(database, settings):
    await _seed_asset(database, lon=37.6273, lat=55.7658)
    job_id = await _seed_job(database)
    async with database.session() as session:
        decision = await DeduplicationService(session, settings).match(
            object_type="telecom_well",
            point=POINT,
            observed_at=datetime(2026, 11, 16, 12, 0, 0, tzinfo=UTC),
            job_id=job_id,
            route_id=None,
            tracking_id=None,
        )
    assert decision.result == DeduplicationResult.NEW_ASSET


async def test_two_nearby_assets_ambiguous(database, settings):
    await _seed_asset(database, lon=37.61730, lat=55.75580)
    await _seed_asset(database, lon=37.61733, lat=55.75582)
    job_id = await _seed_job(database)
    async with database.session() as session:
        decision = await DeduplicationService(session, settings).match(
            object_type="telecom_well",
            point=GeoPoint(37.617315, 55.75581),
            observed_at=datetime(2026, 11, 16, 12, 0, 0, tzinfo=UTC),
            job_id=job_id,
            route_id=None,
            tracking_id=None,
        )
    assert decision.result == DeduplicationResult.AMBIGUOUS
    assert decision.asset_id is None
    assert len(decision.explanation["candidates"]) == 2


async def test_no_gps_without_tracking_new_asset(database, settings):
    job_id = await _seed_job(database)
    async with database.session() as session:
        decision = await DeduplicationService(session, settings).match(
            object_type="telecom_well",
            point=None,
            observed_at=datetime(2026, 11, 16, 12, 0, 0, tzinfo=UTC),
            job_id=job_id,
            route_id=None,
            tracking_id=None,
        )
    assert decision.result == DeduplicationResult.NEW_ASSET
    assert decision.explanation["reason"] == "no_geolocation_and_no_tracking_id"


async def test_candidate_lookup_uses_postgis_distance(database, settings):
    from app.infrastructure.database.repositories.assets import AssetRepository

    near_id = await _seed_asset(database, lon=37.6173, lat=55.7558)
    await _seed_asset(database, lon=37.6173, lat=55.7568)
    async with database.session() as session:
        candidates = await AssetRepository(session).find_candidates(
            point=POINT, radius_m=20, asset_type="telecom_well"
        )
    assert len(candidates) == 1
    asset, distance = candidates[0]
    assert asset.id == near_id
    assert distance < 1.0
