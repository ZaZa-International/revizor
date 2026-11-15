"""Export service integration: CSV/XLSX content correctness."""

from __future__ import annotations

import csv
import io
import uuid
from datetime import UTC, datetime

import pytest
from app.application.services.exports import (
    ASSET_COLUMNS,
    DEFECT_COLUMNS,
    ExportService,
)
from app.domain.enums import DefectStatus, GeolocationStatus
from app.infrastructure.database.models.asset import Asset
from app.infrastructure.database.models.defect import Defect, defect_observations
from app.infrastructure.database.models.job import ProcessingJob
from app.infrastructure.database.models.observation import Observation
from app.infrastructure.database.models.upload import Upload
from app.infrastructure.database.repositories.assets import AssetRepository
from app.infrastructure.database.repositories.defects import DefectRepository
from geoalchemy2 import WKTElement

pytestmark = pytest.mark.integration


async def _seed(database):
    now = datetime.now(UTC)
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
        await session.flush()
        asset = Asset(
            asset_type="telecom_well",
            display_name="Demo well",
            location=WKTElement("POINT(37.6173 55.7558)", srid=4326),
            location_accuracy_m=4.0,
            geolocation_status=GeolocationStatus.CONFIRMED,
            current_condition="damaged_cover",
            current_severity=4,
            current_priority=80.0,
        )
        session.add(asset)
        await session.flush()
        observation = Observation(
            asset_id=asset.id,
            processing_job_id=job.id,
            observed_at=now,
            detected_at=now,
            object_type="telecom_well",
            condition_class="damaged_cover",
            detector_confidence=0.9,
            severity=4,
            geolocation_status=GeolocationStatus.CONFIRMED,
            location=WKTElement("POINT(37.6173 55.7558)", srid=4326),
        )
        session.add(observation)
        await session.flush()
        defect = Defect(
            asset_id=asset.id,
            defect_type="damaged_cover",
            severity=4,
            status=DefectStatus.OPEN,
            first_detected_at=now,
            last_detected_at=now,
        )
        session.add(defect)
        await session.flush()
        await session.execute(
            defect_observations.insert().values(defect_id=defect.id, observation_id=observation.id)
        )
        await session.commit()
        return asset.id, defect.id


async def test_csv_export_assets(database):
    await _seed(database)
    async with database.session() as session:
        service = ExportService(session)
        stmt = AssetRepository(session).filtered_stmt(asset_type="telecom_well")
        rows = await service.asset_rows(stmt)
        content, media_type, filename = service.render(
            rows, ASSET_COLUMNS, "csv", entity="assets", actor_id=None
        )
    assert media_type.startswith("text/csv")
    assert filename.endswith(".csv")
    reader = csv.DictReader(io.StringIO(content.decode("utf-8-sig")))
    data = list(reader)
    assert len(data) == 1
    assert data[0]["asset_type"] == "telecom_well"
    assert float(data[0]["longitude"]) == pytest.approx(37.6173)
    assert float(data[0]["latitude"]) == pytest.approx(55.7558)
    assert "password" not in data[0]


async def test_xlsx_export_defects(database):
    await _seed(database)
    async with database.session() as session:
        service = ExportService(session)
        stmt = DefectRepository(session).filtered_stmt()
        rows = await service.defect_rows(stmt)
        assert rows[0]["observation_count"] == 1
        assert rows[0]["confidence"] == pytest.approx(0.9)
        assert rows[0]["asset_type"] == "telecom_well"
        assert rows[0]["review_status"] == "UNREVIEWED"
        content, media_type, _filename = service.render(
            rows, DEFECT_COLUMNS, "xlsx", entity="defects", actor_id=None
        )
    assert content[:2] == b"PK"
    assert "spreadsheetml" in media_type
    from openpyxl import load_workbook

    workbook = load_workbook(io.BytesIO(content))
    sheet = workbook.active
    header = [cell.value for cell in next(sheet.iter_rows(min_row=1, max_row=1))]
    assert header == DEFECT_COLUMNS
    assert sheet.max_row == 2


async def test_export_respects_filters(database):
    await _seed(database)
    async with database.session() as session:
        service = ExportService(session)
        stmt = AssetRepository(session).filtered_stmt(asset_type="pole")
        rows = await service.asset_rows(stmt)
        assert rows == []
