"""Analytics: overview counters, defect aggregation, grid-based coverage.

Coverage is a transparent heuristic: a fixed grid over the configured survey
area; a cell is covered when >=1 geolocated observation falls into it.
"""

from __future__ import annotations

import math
from typing import Any

from geoalchemy2 import Geometry
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.domain.enums import DefectStatus, ObservationReviewStatus
from app.domain.geospatial.models import BoundingBox
from app.infrastructure.database.models.asset import Asset
from app.infrastructure.database.models.defect import Defect
from app.infrastructure.database.models.job import ProcessingJob
from app.infrastructure.database.models.observation import Observation
from app.infrastructure.database.models.route import Route
from app.infrastructure.database.models.upload import Upload
from app.infrastructure.database.repositories.assets import bbox_element


class AnalyticsService:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self._session = session
        self._settings = settings

    async def _group_count(self, stmt: Any) -> list[dict]:
        rows = (await self._session.execute(stmt)).all()
        return [
            {"key": row[0].value if hasattr(row[0], "value") else row[0], "count": row[1]}
            for row in rows
        ]

    async def overview(self) -> dict:
        assets_total = (await self._session.execute(select(func.count(Asset.id)))).scalar_one()
        observations_total = (
            await self._session.execute(select(func.count(Observation.id)))
        ).scalar_one()
        defects_total = (await self._session.execute(select(func.count(Defect.id)))).scalar_one()
        uploads_total = (await self._session.execute(select(func.count(Upload.id)))).scalar_one()
        routes_total = (await self._session.execute(select(func.count(Route.id)))).scalar_one()
        reviewed = (
            await self._session.execute(
                select(func.count(Observation.id)).where(
                    Observation.review_status != ObservationReviewStatus.UNREVIEWED
                )
            )
        ).scalar_one()
        unlocated_assets = (
            await self._session.execute(
                select(func.count(Asset.id)).where(Asset.location.is_(None))
            )
        ).scalar_one()
        return {
            "assets_total": assets_total,
            "observations_total": observations_total,
            "defects_total": defects_total,
            "uploads_total": uploads_total,
            "routes_total": routes_total,
            "observations_reviewed": reviewed,
            "observations_reviewed_ratio": (
                round(reviewed / observations_total, 4) if observations_total else 0.0
            ),
            "assets_without_location": unlocated_assets,
            "assets_by_type": await self._group_count(
                select(Asset.asset_type, func.count(Asset.id)).group_by(Asset.asset_type)
            ),
            "assets_by_priority_band": await self._group_count(
                select(Asset.priority_band, func.count(Asset.id)).group_by(Asset.priority_band)
            ),
            "defects_by_status": await self._group_count(
                select(Defect.status, func.count(Defect.id)).group_by(Defect.status)
            ),
            "defects_by_severity": await self._group_count(
                select(Defect.severity, func.count(Defect.id)).group_by(Defect.severity)
            ),
            "jobs_by_status": await self._group_count(
                select(ProcessingJob.status, func.count(ProcessingJob.id)).group_by(
                    ProcessingJob.status
                )
            ),
        }

    async def defects_analytics(self) -> dict:
        by_type = (
            await self._session.execute(
                select(
                    Defect.defect_type,
                    func.count(Defect.id),
                    func.avg(Defect.severity),
                    func.count(Defect.id).filter(Defect.status == DefectStatus.CONFIRMED),
                ).group_by(Defect.defect_type)
            )
        ).all()
        open_high = (
            await self._session.execute(
                select(func.count(Defect.id)).where(
                    Defect.status.in_([DefectStatus.OPEN, DefectStatus.CONFIRMED]),
                    Defect.severity >= 4,
                )
            )
        ).scalar_one()
        return {
            "by_type": [
                {
                    "defect_type": row[0],
                    "count": row[1],
                    "avg_severity": round(float(row[2]), 2) if row[2] is not None else None,
                    "confirmed_count": row[3],
                }
                for row in by_type
            ],
            "open_high_severity_count": open_high,
        }

    async def coverage(self) -> dict:
        bbox = BoundingBox.parse(self._settings.demo_area_bbox)
        cell_m = self._settings.coverage_grid_cell_m
        mid_lat = (bbox.min_lat + bbox.max_lat) / 2
        cell_lat = cell_m / 111_320.0
        cell_lon = cell_m / (111_320.0 * max(0.01, math.cos(math.radians(mid_lat))))
        cols = max(1, math.ceil((bbox.max_lon - bbox.min_lon) / cell_lon))
        rows_n = max(1, math.ceil((bbox.max_lat - bbox.min_lat) / cell_lat))

        geo = func.ST_X(Observation.location.cast(Geometry))
        lat = func.ST_Y(Observation.location.cast(Geometry))
        cx = func.floor((geo - bbox.min_lon) / cell_lon)
        cy = func.floor((lat - bbox.min_lat) / cell_lat)
        stmt = (
            select(cx.label("cx"), cy.label("cy"), func.count(Observation.id))
            .where(
                Observation.location.is_not(None),
                func.ST_Intersects(Observation.location, bbox_element(bbox)),
            )
            .group_by(cx, cy)
        )
        cells = (await self._session.execute(stmt)).all()
        covered = len(cells)
        total_cells = cols * rows_n
        route_stats = (
            await self._session.execute(
                select(
                    Route.id,
                    Route.name,
                    func.count(func.distinct(Observation.id)),
                )
                .outerjoin(ProcessingJob, ProcessingJob.route_id == Route.id)
                .outerjoin(Observation, Observation.processing_job_id == ProcessingJob.id)
                .group_by(Route.id, Route.name)
            )
        ).all()
        return {
            "area_bbox": {
                "min_longitude": bbox.min_lon,
                "min_latitude": bbox.min_lat,
                "max_longitude": bbox.max_lon,
                "max_latitude": bbox.max_lat,
            },
            "grid_cell_m": cell_m,
            "grid_cols": cols,
            "grid_rows": rows_n,
            "total_cells": total_cells,
            "covered_cells": covered,
            "coverage_ratio": round(covered / total_cells, 4) if total_cells else 0.0,
            "gap_cells": total_cells - covered,
            "covered_cell_counts": [
                {"cx": row[0], "cy": row[1], "observations": row[2]} for row in cells[:2000]
            ],
            "routes": [
                {
                    "route_id": str(row[0]),
                    "name": row[1],
                    "observations": row[2],
                }
                for row in route_stats
            ],
            "note": "heuristic grid coverage over the configured area; not a road-network model",
        }
