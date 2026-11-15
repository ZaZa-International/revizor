"""Geospatial queries: GeoJSON map layers and nearest-asset search."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from geoalchemy2.shape import to_shape
from shapely.geometry import mapping
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import DefectStatus
from app.domain.geospatial.models import BoundingBox, GeoPoint
from app.infrastructure.database.models.asset import Asset
from app.infrastructure.database.models.defect import Defect
from app.infrastructure.database.models.observation import Observation
from app.infrastructure.database.models.route import Route
from app.infrastructure.database.repositories.assets import (
    AssetRepository,
    bbox_element,
    point_element,
)

MAP_MAX_FEATURES = 5000


def _geojson(element: Any) -> dict | None:
    if element is None:
        return None
    shape = to_shape(element)
    return json.loads(json.dumps(mapping(shape)))


def _feature(geometry: dict | None, properties: dict) -> dict:
    return {"type": "Feature", "geometry": geometry, "properties": properties}


def _collection(features: list[dict]) -> dict:
    return {"type": "FeatureCollection", "features": features}


class GeospatialService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._assets = AssetRepository(session)

    async def map_assets(
        self,
        *,
        bbox: BoundingBox | None = None,
        asset_type: str | None = None,
        priority_band: str | None = None,
        limit: int = MAP_MAX_FEATURES,
    ) -> dict:
        stmt = select(Asset).where(Asset.location.is_not(None))
        if bbox is not None:
            stmt = stmt.where(func.ST_Intersects(Asset.location, bbox_element(bbox)))
        if asset_type is not None:
            stmt = stmt.where(Asset.asset_type == asset_type)
        if priority_band is not None:
            stmt = stmt.where(Asset.priority_band == priority_band)
        stmt = stmt.limit(min(limit, MAP_MAX_FEATURES))
        rows = (await self._session.execute(stmt)).scalars().all()
        features = [
            _feature(
                _geojson(asset.location),
                {
                    "id": str(asset.id),
                    "asset_type": asset.asset_type,
                    "display_name": asset.display_name,
                    "current_condition": asset.current_condition,
                    "current_severity": asset.current_severity,
                    "current_priority": asset.current_priority,
                    "priority_band": asset.priority_band.value if asset.priority_band else None,
                    "geolocation_status": asset.geolocation_status.value,
                    "location_accuracy_m": asset.location_accuracy_m,
                    "lifecycle_status": asset.lifecycle_status.value,
                    "last_observed_at": (
                        asset.last_observed_at.isoformat() if asset.last_observed_at else None
                    ),
                },
            )
            for asset in rows
        ]
        return _collection(features)

    async def map_defects(
        self,
        *,
        bbox: BoundingBox | None = None,
        status: DefectStatus | None = None,
        severity_min: int | None = None,
        limit: int = MAP_MAX_FEATURES,
    ) -> dict:
        stmt = (
            select(Defect, Asset)
            .join(Asset, Defect.asset_id == Asset.id)
            .where(Asset.location.is_not(None))
        )
        if bbox is not None:
            stmt = stmt.where(func.ST_Intersects(Asset.location, bbox_element(bbox)))
        if status is not None:
            stmt = stmt.where(Defect.status == status)
        if severity_min is not None:
            stmt = stmt.where(Defect.severity >= severity_min)
        stmt = stmt.limit(min(limit, MAP_MAX_FEATURES))
        rows = (await self._session.execute(stmt)).all()
        features = [
            _feature(
                _geojson(asset.location),
                {
                    "id": str(defect.id),
                    "asset_id": str(asset.id),
                    "asset_type": asset.asset_type,
                    "defect_type": defect.defect_type,
                    "severity": defect.severity,
                    "status": defect.status.value,
                    "current_priority": asset.current_priority,
                    "first_detected_at": defect.first_detected_at.isoformat(),
                    "last_detected_at": defect.last_detected_at.isoformat(),
                },
            )
            for defect, asset in rows
        ]
        return _collection(features)

    async def map_observations(
        self,
        *,
        bbox: BoundingBox | None = None,
        job_id: str | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        limit: int = MAP_MAX_FEATURES,
    ) -> dict:
        stmt = select(Observation).where(Observation.location.is_not(None))
        if bbox is not None:
            stmt = stmt.where(func.ST_Intersects(Observation.location, bbox_element(bbox)))
        if job_id is not None:
            stmt = stmt.where(Observation.processing_job_id == job_id)
        if date_from is not None:
            stmt = stmt.where(Observation.observed_at >= date_from)
        if date_to is not None:
            stmt = stmt.where(Observation.observed_at <= date_to)
        stmt = stmt.order_by(Observation.observed_at.desc()).limit(min(limit, MAP_MAX_FEATURES))
        rows = (await self._session.execute(stmt)).scalars().all()
        features = [
            _feature(
                _geojson(obs.location),
                {
                    "id": str(obs.id),
                    "asset_id": str(obs.asset_id) if obs.asset_id else None,
                    "object_type": obs.object_type,
                    "condition_class": obs.condition_class,
                    "detector_confidence": obs.detector_confidence,
                    "review_status": obs.review_status.value,
                    "dedup_result": obs.dedup_result.value if obs.dedup_result else None,
                    "observed_at": obs.observed_at.isoformat(),
                    "processing_job_id": str(obs.processing_job_id),
                },
            )
            for obs in rows
        ]
        return _collection(features)

    async def map_routes(self, *, limit: int = MAP_MAX_FEATURES) -> dict:
        stmt = (
            select(Route)
            .where(Route.track_geometry.is_not(None))
            .limit(min(limit, MAP_MAX_FEATURES))
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        features = [
            _feature(
                _geojson(route.track_geometry),
                {
                    "id": str(route.id),
                    "name": route.name,
                    "vehicle_id": route.vehicle_id,
                    "started_at": route.started_at.isoformat() if route.started_at else None,
                    "finished_at": route.finished_at.isoformat() if route.finished_at else None,
                    "total_distance_m": route.total_distance_m,
                },
            )
            for route in rows
        ]
        return _collection(features)

    async def nearest_assets(
        self, *, point: GeoPoint, radius_m: float, asset_type: str | None = None, limit: int = 10
    ) -> list[dict]:
        element = point_element(point)
        stmt = (
            select(Asset, func.ST_Distance(Asset.location, element).label("distance_m"))
            .where(
                Asset.location.is_not(None),
                func.ST_DWithin(Asset.location, element, radius_m),
            )
            .order_by(func.ST_Distance(Asset.location, element).asc())
            .limit(limit)
        )
        if asset_type is not None:
            stmt = stmt.where(Asset.asset_type == asset_type)
        rows = (await self._session.execute(stmt)).all()
        return [
            {
                "id": str(asset.id),
                "asset_type": asset.asset_type,
                "display_name": asset.display_name,
                "distance_m": round(float(distance), 2),
                "current_priority": asset.current_priority,
            }
            for asset, distance in rows
        ]
