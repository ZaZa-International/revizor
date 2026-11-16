# ruff: noqa: RUF001, RUF002  # русскоязычная документация API: кириллица и тире намеренны (ложные срабатывания)
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class RouteCreateRequest(BaseModel):
    """Создание маршрута объезда. Трек — пары [longitude, latitude] (2–10000 точек);
    total_distance_m вычисляется PostGIS (ST_Length, метры). finished_at не может
    быть раньше started_at (naive timestamps трактуются как UTC)."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "name": "Объезд Тверского района, маршрут 1",
                    "vehicle_id": "МГТС-АВ-042",
                    "started_at": "2026-11-15T12:00:00Z",
                    "finished_at": "2026-11-15T13:30:00Z",
                    "track": [[37.6173, 55.7558], [37.6189, 55.7564], [37.6205, 55.7571]],
                    "metadata": {"driver": "Иванов И.И.", "weather": "ясно"},
                }
            ]
        }
    )

    name: str = Field(
        min_length=1,
        max_length=255,
        description="Название маршрута",
        examples=["Объезд Тверского района, маршрут 1"],
    )
    vehicle_id: str | None = Field(
        default=None,
        max_length=64,
        description="Идентификатор транспорта",
        examples=["МГТС-АВ-042"],
    )
    started_at: datetime | None = Field(
        default=None, description="Начало объезда (ISO 8601); поле date_from/date_to для /routes"
    )
    finished_at: datetime | None = Field(
        default=None, description="Окончание объезда; ≥ started_at"
    )
    track: list[list[float]] | None = Field(
        default=None,
        max_length=10000,
        description="Track as [longitude, latitude] pairs (lon/lat order), 2..10000 points",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Произвольные метаданные маршрута (JSON-объект)"
    )

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

    @model_validator(mode="after")
    def _time_order(self) -> RouteCreateRequest:
        if self.started_at is not None and self.finished_at is not None:
            started = self.started_at
            finished = self.finished_at
            if started.tzinfo is None:
                started = started.replace(tzinfo=UTC)
            if finished.tzinfo is None:
                finished = finished.replace(tzinfo=UTC)
            if finished < started:
                raise ValueError("finished_at must be later than or equal to started_at")
        return self


class RouteResponse(BaseModel):
    """Маршрут объезда. track_geojson (LineString) возвращается в POST /routes
    и GET /routes/{id}; в списке маршрутов трек не включается."""

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        json_schema_extra={
            "examples": [
                {
                    "id": "d4e5f6a7-b8c9-4d0e-1f2a-3b4c5d6e7f80",
                    "name": "Объезд Тверского района, маршрут 1",
                    "vehicle_id": "МГТС-АВ-042",
                    "started_at": "2026-11-15T12:00:00Z",
                    "finished_at": "2026-11-15T13:30:00Z",
                    "total_distance_m": 4321.8,
                    "metadata": {"driver": "Иванов И.И.", "weather": "ясно"},
                    "created_at": "2026-11-15T13:35:00Z",
                    "updated_at": "2026-11-15T13:35:00Z",
                    "track_geojson": {
                        "type": "LineString",
                        "coordinates": [
                            [37.6173, 55.7558],
                            [37.6189, 55.7564],
                            [37.6205, 55.7571],
                        ],
                    },
                }
            ]
        },
    )

    id: uuid.UUID = Field(description="Идентификатор маршрута (UUID)")
    name: str = Field(description="Название маршрута")
    vehicle_id: str | None = Field(description="Идентификатор транспорта")
    started_at: datetime | None = Field(description="Начало объезда")
    finished_at: datetime | None = Field(description="Окончание объезда")
    total_distance_m: float | None = Field(
        description="Длина трека в метрах (PostGIS ST_Length по geography)", examples=[4321.8]
    )
    metadata: dict[str, Any] = Field(
        validation_alias="metadata_", description="Произвольные метаданные маршрута"
    )
    created_at: datetime = Field(description="Дата создания записи")
    updated_at: datetime = Field(description="Дата последнего обновления")
    track_geojson: dict[str, Any] | None = Field(
        default=None,
        description="Трек как GeoJSON LineString (координаты [lon, lat]); "
        "null, если трек не задан или не запрошен",
    )
