from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class RouteCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    vehicle_id: str | None = Field(default=None, max_length=64)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    track: list[list[float]] | None = Field(
        default=None, description="List of [longitude, latitude] pairs, >=2 points"
    )
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _track_valid(self) -> RouteCreateRequest:
        if self.track is not None:
            if len(self.track) < 2:
                raise ValueError("track must contain at least 2 points")
            for pair in self.track:
                if len(pair) != 2:
                    raise ValueError("track points must be [longitude, latitude]")
                lon, lat = pair
                if not (-180 <= lon <= 180 and -90 <= lat <= 90):
                    raise ValueError("track coordinates out of range (lon, lat order)")
        return self


class RouteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: uuid.UUID
    name: str
    vehicle_id: str | None
    started_at: datetime | None
    finished_at: datetime | None
    total_distance_m: float | None
    metadata: dict[str, Any] = Field(validation_alias="metadata_")
    created_at: datetime
    updated_at: datetime
    track_geojson: dict[str, Any] | None = None
