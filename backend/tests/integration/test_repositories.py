"""Repository + PostGIS constraint tests on a real database."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from app.core.exceptions import ConflictError
from app.domain.enums import GeolocationStatus
from app.infrastructure.database.models.asset import Asset
from app.infrastructure.database.models.job import ProcessingJob
from app.infrastructure.database.models.observation import Observation
from app.infrastructure.database.models.upload import Upload
from app.infrastructure.database.repositories.assets import AssetRepository
from geoalchemy2 import WKTElement
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

pytestmark = pytest.mark.integration


async def _job(database) -> uuid.UUID:
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


async def test_asset_version_conflict(database):
    async with database.session() as session:
        repo = AssetRepository(session)
        asset = Asset(asset_type="telecom_well", geolocation_status=GeolocationStatus.UNAVAILABLE)
        repo.add(asset)
        await session.commit()
        await repo.update_with_version(asset, expected_version=1, values={"display_name": "A"})
        await session.commit()
        assert asset.version == 2
        with pytest.raises(ConflictError):
            await repo.update_with_version(asset, expected_version=1, values={"display_name": "B"})


async def test_observation_duplicate_detection_rejected(database):
    job_id = await _job(database)
    detection_id = uuid.uuid4()
    now = datetime.now(UTC)
    async with database.session() as session:
        with pytest.raises(IntegrityError):
            for _ in range(2):
                session.add(
                    Observation(
                        processing_job_id=job_id,
                        detection_id=detection_id,
                        observed_at=now,
                        detected_at=now,
                        object_type="telecom_well",
                        detector_confidence=0.9,
                        geolocation_status=GeolocationStatus.UNAVAILABLE,
                    )
                )
                await session.flush()
            await session.commit()


async def test_severity_check_constraint(database):
    async with database.session() as session:
        session.add(
            Asset(
                asset_type="telecom_well",
                current_severity=6,
                geolocation_status=GeolocationStatus.UNAVAILABLE,
            )
        )
        with pytest.raises(IntegrityError):
            await session.commit()


async def test_confidence_check_constraint(database):
    job_id = await _job(database)
    now = datetime.now(UTC)
    async with database.session() as session:
        session.add(
            Observation(
                processing_job_id=job_id,
                observed_at=now,
                detected_at=now,
                object_type="telecom_well",
                detector_confidence=1.5,
                geolocation_status=GeolocationStatus.UNAVAILABLE,
            )
        )
        with pytest.raises(IntegrityError):
            await session.commit()


async def test_location_status_consistency_constraint(database):
    async with database.session() as session:
        session.add(
            Asset(
                asset_type="telecom_well",
                location=WKTElement("POINT(37.6 55.75)", srid=4326),
                geolocation_status=GeolocationStatus.UNAVAILABLE,
            )
        )
        with pytest.raises(IntegrityError):
            await session.commit()


async def test_bbox_filter(database):
    from app.domain.geospatial.models import BoundingBox

    async with database.session() as session:
        repo = AssetRepository(session)
        repo.add(
            Asset(
                asset_type="telecom_well",
                location=WKTElement("POINT(37.6173 55.7558)", srid=4326),
                geolocation_status=GeolocationStatus.CONFIRMED,
            )
        )
        repo.add(
            Asset(
                asset_type="pole",
                location=WKTElement("POINT(37.9 55.9)", srid=4326),
                geolocation_status=GeolocationStatus.CONFIRMED,
            )
        )
        await session.commit()
        stmt = repo.filtered_stmt(bbox=BoundingBox.parse("37.5,55.7,37.7,55.8"))
        rows = (await session.execute(stmt)).scalars().all()
        assert len(rows) == 1
        assert rows[0].asset_type == "telecom_well"


async def test_geography_distance_is_meters(database):
    from geoalchemy2 import Geography
    from sqlalchemy import cast, func

    async with database.session() as session:
        p1 = cast(WKTElement("POINT(37.6173 55.7558)", srid=4326), Geography)
        p2 = cast(WKTElement("POINT(37.6173 55.7567)", srid=4326), Geography)
        distance = (await session.execute(select(func.ST_Distance(p1, p2)))).scalar_one()
        assert 95 < float(distance) < 105
