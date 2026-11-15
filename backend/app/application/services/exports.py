"""CSV / XLSX exports with the same filters as list endpoints.

Secrets and internal technical fields are never exported.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from geoalchemy2.shape import to_shape
from openpyxl import Workbook
from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import AuditAction
from app.infrastructure.database.models.asset import Asset
from app.infrastructure.database.models.defect import Defect, defect_observations
from app.infrastructure.database.models.observation import Observation
from app.infrastructure.database.models.review import Review
from app.infrastructure.database.repositories.users import AuditRepository

EXPORT_ROW_LIMIT = 50_000

ASSET_COLUMNS = [
    "id",
    "external_id",
    "asset_type",
    "display_name",
    "longitude",
    "latitude",
    "location_accuracy_m",
    "geolocation_status",
    "current_condition",
    "current_severity",
    "current_priority",
    "priority_band",
    "lifecycle_status",
    "first_observed_at",
    "last_observed_at",
]
OBSERVATION_COLUMNS = [
    "id",
    "asset_id",
    "processing_job_id",
    "observed_at",
    "object_type",
    "condition_class",
    "detector_confidence",
    "severity",
    "review_status",
    "dedup_result",
    "longitude",
    "latitude",
    "geolocation_status",
    "model_name",
    "model_version",
]
DEFECT_COLUMNS = [
    "id",
    "asset_id",
    "asset_type",
    "defect_type",
    "severity",
    "status",
    "priority",
    "confidence",
    "longitude",
    "latitude",
    "location_accuracy_m",
    "review_status",
    "first_detected_at",
    "last_detected_at",
    "observation_count",
]


def _lonlat(location: Any) -> tuple[float | None, float | None]:
    if location is None:
        return None, None
    shape = to_shape(location)
    return float(shape.x), float(shape.y)


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


class ExportService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._audit = AuditRepository(session)

    async def _rows(self, stmt: Select[Any]) -> Sequence[Any]:
        return (await self._session.execute(stmt.limit(EXPORT_ROW_LIMIT))).all()

    async def asset_rows(self, stmt: Select[tuple[Asset]]) -> list[dict]:
        rows = await self._rows(stmt)
        result = []
        for (asset,) in rows:
            lon, lat = _lonlat(asset.location)
            result.append(
                {
                    "id": str(asset.id),
                    "external_id": asset.external_id,
                    "asset_type": asset.asset_type,
                    "display_name": asset.display_name,
                    "longitude": lon,
                    "latitude": lat,
                    "location_accuracy_m": asset.location_accuracy_m,
                    "geolocation_status": asset.geolocation_status.value,
                    "current_condition": asset.current_condition,
                    "current_severity": asset.current_severity,
                    "current_priority": asset.current_priority,
                    "priority_band": asset.priority_band.value if asset.priority_band else None,
                    "lifecycle_status": asset.lifecycle_status.value,
                    "first_observed_at": _iso(asset.first_observed_at),
                    "last_observed_at": _iso(asset.last_observed_at),
                }
            )
        return result

    async def observation_rows(self, stmt: Select[tuple[Observation]]) -> list[dict]:
        rows = await self._rows(stmt)
        result = []
        for (obs,) in rows:
            lon, lat = _lonlat(obs.location)
            result.append(
                {
                    "id": str(obs.id),
                    "asset_id": str(obs.asset_id) if obs.asset_id else None,
                    "processing_job_id": str(obs.processing_job_id),
                    "observed_at": _iso(obs.observed_at),
                    "object_type": obs.object_type,
                    "condition_class": obs.condition_class,
                    "detector_confidence": obs.detector_confidence,
                    "severity": obs.severity,
                    "review_status": obs.review_status.value,
                    "dedup_result": obs.dedup_result.value if obs.dedup_result else None,
                    "longitude": lon,
                    "latitude": lat,
                    "geolocation_status": obs.geolocation_status.value,
                    "model_name": obs.model_name,
                    "model_version": obs.model_version,
                }
            )
        return result

    async def defect_rows(self, stmt: Select[tuple[Defect]]) -> list[dict]:
        obs_agg = (
            select(
                defect_observations.c.defect_id.label("defect_id"),
                func.count(defect_observations.c.observation_id).label("obs_count"),
                func.max(Observation.detector_confidence).label("max_conf"),
            )
            .join(
                Observation,
                Observation.id == defect_observations.c.observation_id,
            )
            .group_by(defect_observations.c.defect_id)
            .subquery()
        )
        latest_review = (
            select(Review.decision)
            .where(Review.defect_id == Defect.id)
            .order_by(Review.reviewed_at.desc())
            .limit(1)
            .scalar_subquery()
        )
        joined = (
            stmt.add_columns(
                Asset.asset_type,
                Asset.location,
                Asset.location_accuracy_m,
                Asset.current_priority,
                obs_agg.c.obs_count,
                obs_agg.c.max_conf,
                latest_review.label("latest_review"),
            )
            .join(Asset, Defect.asset_id == Asset.id)
            .outerjoin(obs_agg, obs_agg.c.defect_id == Defect.id)
        )
        rows = (await self._session.execute(joined.limit(EXPORT_ROW_LIMIT))).all()
        result = []
        for row in rows:
            defect = row[0]
            lon, lat = _lonlat(row[2])
            result.append(
                {
                    "id": str(defect.id),
                    "asset_id": str(defect.asset_id),
                    "asset_type": row[1],
                    "defect_type": defect.defect_type,
                    "severity": defect.severity,
                    "status": defect.status.value,
                    "priority": row[4],
                    "confidence": float(row[6]) if row[6] is not None else None,
                    "longitude": lon,
                    "latitude": lat,
                    "location_accuracy_m": row[3],
                    "review_status": row[7].value if row[7] is not None else "UNREVIEWED",
                    "first_detected_at": _iso(defect.first_detected_at),
                    "last_detected_at": _iso(defect.last_detected_at),
                    "observation_count": row[5] or 0,
                }
            )
        return result

    def render(
        self, rows: list[dict], columns: list[str], fmt: str, *, entity: str, actor_id: Any
    ) -> tuple[bytes, str, str]:
        stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
        filename = f"{entity}-export-{stamp}.{fmt}"
        if fmt == "csv":
            buffer = io.StringIO()
            writer = csv.DictWriter(buffer, fieldnames=columns, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
            content = buffer.getvalue().encode("utf-8-sig")
            media_type = "text/csv; charset=utf-8"
        elif fmt == "xlsx":
            workbook = Workbook(write_only=True)
            sheet = workbook.create_sheet(title=entity[:31])
            sheet.append(columns)
            for row in rows:
                sheet.append([row.get(col) for col in columns])
            out = io.BytesIO()
            workbook.save(out)
            content = out.getvalue()
            media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        else:
            raise ValueError(f"Unsupported export format: {fmt}")
        self._audit.record(
            actor_id=actor_id,
            action=AuditAction.EXPORT.value,
            entity_type=entity,
            entity_id=None,
            after_state={"format": fmt, "rows": len(rows)},
        )
        return content, media_type, filename
