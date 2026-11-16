"""Survey route writes: WKT track construction, PostGIS length, audit.

ST_Length is computed on the geography literal BEFORE insert (one round trip,
no post-flush update); distances are meters (geography, SRID 4326).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from geoalchemy2 import Geography, WKTElement
from sqlalchemy import cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import AuditAction
from app.infrastructure.database.models.route import Route
from app.infrastructure.database.repositories.routes import RouteRepository
from app.infrastructure.database.repositories.users import AuditRepository


class RouteService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._routes = RouteRepository(session)
        self._audit = AuditRepository(session)

    async def create_route(
        self,
        *,
        name: str,
        vehicle_id: str | None,
        started_at: datetime | None,
        finished_at: datetime | None,
        track: list[list[float]] | None,
        metadata: dict,
        actor_id: uuid.UUID | None,
    ) -> Route:
        track_element = None
        distance: float | None = None
        if track:
            coords = ", ".join(f"{lon} {lat}" for lon, lat in track)
            track_element = WKTElement(f"LINESTRING({coords})", srid=4326)
            length = (
                await self._session.execute(select(func.ST_Length(cast(track_element, Geography))))
            ).scalar_one()
            distance = float(length)
        route = Route(
            name=name,
            vehicle_id=vehicle_id,
            started_at=started_at,
            finished_at=finished_at,
            track_geometry=track_element,
            total_distance_m=distance,
            metadata_=metadata,
        )
        self._routes.add(route)
        await self._session.flush()
        self._audit.record(
            actor_id=actor_id,
            action=AuditAction.CREATE.value,
            entity_type="route",
            entity_id=route.id,
            after_state={
                "name": name,
                "vehicle_id": vehicle_id,
                "has_track": track_element is not None,
                "total_distance_m": distance,
            },
        )
        return route
