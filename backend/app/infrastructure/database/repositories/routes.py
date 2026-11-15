from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Select, select

from app.infrastructure.database.models.route import Route
from app.infrastructure.database.repositories.base import (
    BaseRepository,
    Page,
    apply_sorting,
    paginate,
)


class RouteRepository(BaseRepository[Route]):
    model = Route
    entity_name = "Route"

    def filtered_stmt(
        self,
        *,
        vehicle_id: str | None = None,
        search: str | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
    ) -> Select[Any]:
        stmt = select(Route)
        if vehicle_id is not None:
            stmt = stmt.where(Route.vehicle_id == vehicle_id)
        if search:
            stmt = stmt.where(Route.name.ilike(f"%{search}%"))
        if date_from is not None:
            stmt = stmt.where(Route.started_at >= date_from)
        if date_to is not None:
            stmt = stmt.where(Route.started_at <= date_to)
        return stmt

    async def list_paginated(
        self,
        stmt: Select[Any],
        *,
        page: int,
        page_size: int,
        sort_by: str | None,
        order: str,
    ) -> Page[Route]:
        stmt = apply_sorting(
            stmt,
            Route,
            sort_by,
            order,
            {
                "created_at": Route.created_at,
                "started_at": Route.started_at,
                "name": Route.name,
                "total_distance_m": Route.total_distance_m,
            },
        )
        return await paginate(self.session, stmt, page=page, page_size=page_size)
