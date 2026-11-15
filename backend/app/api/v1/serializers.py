"""ORM -> API schema conversion with geo/URL enrichment (no ORM in responses)."""

from __future__ import annotations

import json
from typing import Any

from geoalchemy2.shape import to_shape
from shapely.geometry import mapping
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.interfaces.storage import ObjectStorage
from app.infrastructure.database.models.asset import Asset
from app.infrastructure.database.models.observation import Observation
from app.infrastructure.database.models.route import Route
from app.infrastructure.database.models.stored_file import StoredFile
from app.schemas.assets import AssetResponse, ObservationResponse
from app.schemas.routes import RouteResponse


def lonlat(location: Any) -> tuple[float | None, float | None]:
    if location is None:
        return None, None
    shape = to_shape(location)
    return float(shape.x), float(shape.y)


def asset_response(asset: Asset) -> AssetResponse:
    lon, lat = lonlat(asset.location)
    response = AssetResponse.model_validate(asset)
    response.longitude = lon
    response.latitude = lat
    return response


async def _safe_url(storage: ObjectStorage, key: str) -> str | None:
    try:
        return await storage.generate_presigned_url(key)
    except Exception:
        return None


async def observation_response(
    observation: Observation, session: AsyncSession, storage: ObjectStorage
) -> ObservationResponse:
    lon, lat = lonlat(observation.location)
    response = ObservationResponse.model_validate(observation)
    response.longitude = lon
    response.latitude = lat
    if observation.image_id is not None:
        stored = await session.get(StoredFile, observation.image_id)
        if stored is not None:
            response.image_url = await _safe_url(storage, stored.storage_key)
    if observation.crop_image_id is not None:
        stored = await session.get(StoredFile, observation.crop_image_id)
        if stored is not None:
            response.crop_url = await _safe_url(storage, stored.storage_key)
    return response


def route_response(route: Route, *, with_track: bool = False) -> RouteResponse:
    response = RouteResponse.model_validate(route)
    if with_track and route.track_geometry is not None:
        response.track_geojson = json.loads(json.dumps(mapping(to_shape(route.track_geometry))))
    return response
