"""ORM -> API schema conversion with geo/URL enrichment (no ORM in responses).

Read-side enrichment intentionally queries via session/repositories directly
(documented read-via-repo pattern); all writes go through application services.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Sequence
from typing import Any

from geoalchemy2.shape import to_shape
from shapely.geometry import mapping
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.interfaces.storage import ObjectStorage
from app.infrastructure.database.models.asset import Asset
from app.infrastructure.database.models.defect import Defect
from app.infrastructure.database.models.observation import Observation
from app.infrastructure.database.models.route import Route
from app.infrastructure.database.models.stored_file import StoredFile
from app.infrastructure.database.repositories.defects import DefectRepository
from app.schemas.assets import AssetResponse, DefectResponse, ObservationResponse
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


async def _stored_files_by_id(
    session: AsyncSession, file_ids: set[uuid.UUID]
) -> dict[uuid.UUID, StoredFile]:
    if not file_ids:
        return {}
    stmt = select(StoredFile).where(StoredFile.id.in_(file_ids))
    rows = (await session.execute(stmt)).scalars().all()
    return {stored.id: stored for stored in rows}


async def observation_responses(
    observations: Sequence[Observation],
    session: AsyncSession,
    storage: ObjectStorage,
    *,
    include_media: bool = True,
) -> list[ObservationResponse]:
    """Batch serialization: ONE StoredFile SELECT for the whole page.

    Presigning stays per-key (the storage port is async); a single batched
    presign call is future work. include_media=False skips URLs entirely
    (VIEWER gating via can_access_media at the router).
    """
    responses: list[ObservationResponse] = []
    file_ids: set[uuid.UUID] = set()
    for observation in observations:
        lon, lat = lonlat(observation.location)
        response = ObservationResponse.model_validate(observation)
        response.longitude = lon
        response.latitude = lat
        responses.append(response)
        if include_media:
            if observation.image_id is not None:
                file_ids.add(observation.image_id)
            if observation.crop_image_id is not None:
                file_ids.add(observation.crop_image_id)
    if not include_media or not file_ids:
        return responses
    stored = await _stored_files_by_id(session, file_ids)
    urls: dict[str, str | None] = {}
    for observation, response in zip(observations, responses, strict=True):
        for file_id, attr in (
            (observation.image_id, "image_url"),
            (observation.crop_image_id, "crop_url"),
        ):
            if file_id is None:
                continue
            file = stored.get(file_id)
            if file is None:
                continue
            if file.storage_key not in urls:
                urls[file.storage_key] = await _safe_url(storage, file.storage_key)
            setattr(response, attr, urls[file.storage_key])
    return responses


async def observation_response(
    observation: Observation,
    session: AsyncSession,
    storage: ObjectStorage,
    *,
    include_media: bool = True,
) -> ObservationResponse:
    responses = await observation_responses(
        [observation], session, storage, include_media=include_media
    )
    return responses[0]


async def defect_responses(
    defects: Sequence[Defect], session: AsyncSession
) -> list[DefectResponse]:
    """Batch serialization with ONE GROUP BY observation-count query."""
    counts = await DefectRepository(session).observation_counts([defect.id for defect in defects])
    responses = []
    for defect in defects:
        response = DefectResponse.model_validate(defect)
        response.observation_count = counts.get(defect.id, 0)
        responses.append(response)
    return responses


async def defect_response(defect: Defect, session: AsyncSession) -> DefectResponse:
    responses = await defect_responses([defect], session)
    return responses[0]


def route_response(route: Route, *, with_track: bool = False) -> RouteResponse:
    response = RouteResponse.model_validate(route)
    if with_track and route.track_geometry is not None:
        response.track_geojson = json.loads(json.dumps(mapping(to_shape(route.track_geometry))))
    return response
