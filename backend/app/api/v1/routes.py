from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Query
from geoalchemy2 import WKTElement
from sqlalchemy import func, select

from app.api.v1.serializers import route_response
from app.dependencies import CurrentUser, OperatorOrAdmin, SessionDep
from app.infrastructure.database.models.route import Route
from app.infrastructure.database.repositories.routes import RouteRepository
from app.schemas.common import PageResponse
from app.schemas.routes import RouteCreateRequest, RouteResponse

router = APIRouter(prefix="/routes", tags=["routes"])


@router.post("", response_model=RouteResponse, status_code=201, summary="Create survey route")
async def create_route(
    body: RouteCreateRequest, session: SessionDep, user: OperatorOrAdmin
) -> RouteResponse:
    track_element = None
    if body.track:
        coords = ", ".join(f"{lon} {lat}" for lon, lat in body.track)
        track_element = WKTElement(f"LINESTRING({coords})", srid=4326)
    route = Route(
        name=body.name,
        vehicle_id=body.vehicle_id,
        started_at=body.started_at,
        finished_at=body.finished_at,
        track_geometry=track_element,
        metadata_=body.metadata,
    )
    repo = RouteRepository(session)
    repo.add(route)
    await session.flush()
    if track_element is not None:
        distance = (
            await session.execute(
                select(func.ST_Length(Route.track_geometry)).where(Route.id == route.id)
            )
        ).scalar_one()
        route.total_distance_m = float(distance)
        await session.flush()
    return route_response(route, with_track=True)


@router.get("", response_model=PageResponse[RouteResponse], summary="List routes")
async def list_routes(
    session: SessionDep,
    user: CurrentUser,
    vehicle_id: str | None = None,
    search: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    sort_by: str | None = None,
    order: Literal["asc", "desc"] = "desc",
) -> dict:
    repo = RouteRepository(session)
    stmt = repo.filtered_stmt(
        vehicle_id=vehicle_id, search=search, date_from=date_from, date_to=date_to
    )
    result = await repo.list_paginated(
        stmt, page=page, page_size=page_size, sort_by=sort_by, order=order
    )
    return {
        "items": [route_response(route).model_dump(mode="json") for route in result.items],
        "total": result.total,
        "page": result.page,
        "page_size": result.page_size,
        "pages": result.pages,
    }


@router.get("/{route_id}", response_model=RouteResponse, summary="Get route with track GeoJSON")
async def get_route(route_id: uuid.UUID, session: SessionDep, user: CurrentUser) -> RouteResponse:
    route = await RouteRepository(session).get_or_raise(route_id)
    return route_response(route, with_track=True)
