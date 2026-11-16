from __future__ import annotations

from datetime import datetime
from typing import Any

from geoalchemy2 import WKTElement
from sqlalchemy import Select, func, select, update

from app.domain.enums import GeolocationStatus, LifecycleStatus, PriorityBand
from app.domain.geospatial.models import BoundingBox, GeoPoint
from app.infrastructure.database.models.asset import Asset
from app.infrastructure.database.repositories.base import (
    BaseRepository,
    Page,
    apply_sorting,
    like_contains,
    paginate,
)


def point_element(point: GeoPoint) -> WKTElement:
    return WKTElement(point.to_wkt(), srid=4326)


def bbox_element(bbox: BoundingBox) -> WKTElement:
    return WKTElement(bbox.to_wkt_polygon(), srid=4326)


class AssetRepository(BaseRepository[Asset]):
    model = Asset
    entity_name = "Asset"

    async def get_by_external_id(self, external_id: str) -> Asset | None:
        stmt = select(Asset).where(Asset.external_id == external_id)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    def filtered_stmt(
        self,
        *,
        asset_type: str | None = None,
        geolocation_status: GeolocationStatus | None = None,
        lifecycle_status: LifecycleStatus | None = None,
        priority_band: PriorityBand | None = None,
        bbox: BoundingBox | None = None,
        search: str | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
    ) -> Select[Any]:
        stmt = select(Asset)
        if asset_type is not None:
            stmt = stmt.where(Asset.asset_type == asset_type)
        if geolocation_status is not None:
            stmt = stmt.where(Asset.geolocation_status == geolocation_status)
        if lifecycle_status is not None:
            stmt = stmt.where(Asset.lifecycle_status == lifecycle_status)
        if priority_band is not None:
            stmt = stmt.where(Asset.priority_band == priority_band)
        if bbox is not None:
            stmt = stmt.where(
                Asset.location.is_not(None),
                func.ST_Intersects(Asset.location, bbox_element(bbox)),
            )
        if search:
            pattern = like_contains(search)
            stmt = stmt.where(
                Asset.display_name.ilike(pattern, escape="\\")
                | Asset.external_id.ilike(pattern, escape="\\")
            )
        if date_from is not None:
            stmt = stmt.where(Asset.last_observed_at >= date_from)
        if date_to is not None:
            stmt = stmt.where(Asset.last_observed_at <= date_to)
        return stmt

    async def list_paginated(
        self,
        stmt: Select[Any],
        *,
        page: int,
        page_size: int,
        sort_by: str | None,
        order: str,
    ) -> Page[Asset]:
        stmt = apply_sorting(
            stmt,
            Asset,
            sort_by,
            order,
            {
                "created_at": Asset.created_at,
                "last_observed_at": Asset.last_observed_at,
                "current_priority": Asset.current_priority,
                "current_severity": Asset.current_severity,
                "asset_type": Asset.asset_type,
            },
        )
        return await paginate(self.session, stmt, page=page, page_size=page_size)

    async def find_candidates(
        self,
        *,
        point: GeoPoint,
        radius_m: float,
        asset_type: str,
        limit: int = 10,
    ) -> list[tuple[Asset, float]]:
        """Spatial candidate lookup fully inside PostGIS (GiST + ST_DWithin)."""
        element = point_element(point)
        stmt = (
            select(Asset, func.ST_Distance(Asset.location, element).label("distance_m"))
            .where(
                Asset.location.is_not(None),
                Asset.asset_type == asset_type,
                Asset.lifecycle_status == LifecycleStatus.ACTIVE,
                func.ST_DWithin(Asset.location, element, radius_m),
            )
            .order_by(func.ST_Distance(Asset.location, element).asc())
            .limit(limit)
        )
        rows = (await self.session.execute(stmt)).all()
        return [(row[0], float(row[1])) for row in rows]

    async def update_with_version(
        self, asset: Asset, expected_version: int, values: dict[str, Any]
    ) -> Asset:
        from app.core.exceptions import ConflictError

        stmt = (
            update(Asset)
            .where(Asset.id == asset.id, Asset.version == expected_version)
            .values(**values, version=expected_version + 1)
            .returning(Asset.id)
        )
        result = await self.session.execute(stmt)
        if result.first() is None:
            raise ConflictError("Asset was modified concurrently; reload and retry")
        await self.session.refresh(asset)
        return asset
