"""Typed GeoJSON response models (RFC 7946).

Coordinate order is ALWAYS [longitude, latitude]; geometry types mirror the
output of application/services/geospatial.py exactly.
"""
# ruff: noqa: RUF001  # русскоязычная документация API: кириллица и тире намеренны (ложные срабатывания)

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field

from app.domain.enums import (
    DeduplicationResult,
    DefectStatus,
    GeolocationStatus,
    LifecycleStatus,
    ObservationReviewStatus,
    PriorityBand,
)

PropertiesT = TypeVar("PropertiesT", bound=BaseModel)


class GeoJSONPoint(BaseModel):
    """Точка GeoJSON (RFC 7946)."""

    model_config = ConfigDict(
        json_schema_extra={"examples": [{"type": "Point", "coordinates": [37.6173, 55.7558]}]}
    )

    type: Literal["Point"] = "Point"
    coordinates: list[float] = Field(description="[longitude, latitude] (RFC 7946 order)")


class GeoJSONLineString(BaseModel):
    """Линия GeoJSON (трек маршрута, RFC 7946)."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "type": "LineString",
                    "coordinates": [[37.6173, 55.7558], [37.6189, 55.7564], [37.6205, 55.7571]],
                }
            ]
        }
    )

    type: Literal["LineString"] = "LineString"
    coordinates: list[list[float]] = Field(
        description="Ordered [longitude, latitude] pairs (RFC 7946 order)"
    )


GeoJSONGeometry = Annotated[GeoJSONPoint | GeoJSONLineString, Field(discriminator="type")]


class Feature(BaseModel, Generic[PropertiesT]):
    """GeoJSON Feature: геометрия + properties, специфичные для слоя."""

    type: Literal["Feature"] = "Feature"
    geometry: GeoJSONGeometry | None = Field(
        description="Point для активов/дефектов/наблюдений, LineString для маршрутов; "
        "null, если геометрия отсутствует"
    )
    properties: PropertiesT = Field(description="Атрибуты объекта (схема зависит от слоя)")


class FeatureCollection(BaseModel, Generic[PropertiesT]):
    """GeoJSON FeatureCollection (RFC 7946) — формат всех map-слоёв.

    Пример ниже иллюстрирует слой /map/assets; для /map/defects, /map/observations
    и /map/routes схема properties отличается (см. соответствующие *MapProperties).
    Объекты без GPS (UNAVAILABLE) в слои не включаются."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "type": "FeatureCollection",
                    "features": [
                        {
                            "type": "Feature",
                            "geometry": {"type": "Point", "coordinates": [37.6173, 55.7558]},
                            "properties": {
                                "id": "3f2b8c1e-9d4a-4f6b-8e2c-1a5d7b9f0c34",
                                "asset_type": "telecom_well",
                                "display_name": "Колодец у дома 12 по ул. Тверская",
                                "current_condition": "missing_cover",
                                "current_severity": 5,
                                "current_priority": 87.5,
                                "priority_band": "HIGH_PRIORITY",
                                "geolocation_status": "CONFIRMED",
                                "location_accuracy_m": 4.0,
                                "lifecycle_status": "ACTIVE",
                                "last_observed_at": "2026-11-15T12:00:00Z",
                            },
                        }
                    ],
                }
            ]
        }
    )

    type: Literal["FeatureCollection"] = "FeatureCollection"
    features: list[Feature[PropertiesT]] = Field(
        description="Объекты слоя (не более limit; порядок детерминирован)"
    )


class AssetMapProperties(BaseModel):
    """Properties слоя /map/assets."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "id": "3f2b8c1e-9d4a-4f6b-8e2c-1a5d7b9f0c34",
                    "asset_type": "telecom_well",
                    "display_name": "Колодец у дома 12 по ул. Тверская",
                    "current_condition": "missing_cover",
                    "current_severity": 5,
                    "current_priority": 87.5,
                    "priority_band": "HIGH_PRIORITY",
                    "geolocation_status": "CONFIRMED",
                    "location_accuracy_m": 4.0,
                    "lifecycle_status": "ACTIVE",
                    "last_observed_at": "2026-11-15T12:00:00Z",
                }
            ]
        }
    )

    id: str = Field(description="Идентификатор актива (UUID строкой)")
    asset_type: str = Field(description="Тип объекта", examples=["telecom_well"])
    display_name: str | None = Field(description="Отображаемое имя")
    current_condition: str | None = Field(
        description="Текущее состояние", examples=["missing_cover"]
    )
    current_severity: int | None = Field(description="Тяжесть 1–5", examples=[5])
    current_priority: float | None = Field(description="Приоритет 0–100", examples=[87.5])
    priority_band: PriorityBand | None = Field(description="Полоса приоритета")
    geolocation_status: GeolocationStatus = Field(description="Достоверность геопривязки")
    location_accuracy_m: float | None = Field(description="Точность координат, м")
    lifecycle_status: LifecycleStatus = Field(description="Жизненный цикл объекта")
    last_observed_at: datetime | None = Field(description="Последнее наблюдение")


class DefectMapProperties(BaseModel):
    """Properties слоя /map/defects (геометрия — точка актива)."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "id": "e5f6a7b8-c9d0-4e1f-2a3b-4c5d6e7f8091",
                    "asset_id": "3f2b8c1e-9d4a-4f6b-8e2c-1a5d7b9f0c34",
                    "asset_type": "telecom_well",
                    "defect_type": "missing_cover",
                    "severity": 5,
                    "status": "OPEN",
                    "current_priority": 87.5,
                    "first_detected_at": "2026-11-15T12:00:07Z",
                    "last_detected_at": "2026-11-15T12:00:07Z",
                }
            ]
        }
    )

    id: str = Field(description="Идентификатор дефекта (UUID строкой)")
    asset_id: str = Field(description="Идентификатор актива")
    asset_type: str = Field(description="Тип объекта", examples=["telecom_well"])
    defect_type: str = Field(description="Тип дефекта", examples=["missing_cover"])
    severity: int = Field(description="Тяжесть 1–5", examples=[5])
    status: DefectStatus = Field(description="Статус дефекта")
    current_priority: float | None = Field(description="Приоритет актива 0–100", examples=[87.5])
    first_detected_at: datetime = Field(description="Первое обнаружение")
    last_detected_at: datetime = Field(description="Последнее обнаружение")


class ObservationMapProperties(BaseModel):
    """Properties слоя /map/observations."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "id": "7c1e9a2b-4d5f-4a8c-9b3e-2f6a8d0c1e57",
                    "asset_id": "3f2b8c1e-9d4a-4f6b-8e2c-1a5d7b9f0c34",
                    "object_type": "telecom_well",
                    "condition_class": "missing_cover",
                    "detector_confidence": 0.93,
                    "review_status": "UNREVIEWED",
                    "dedup_result": "MATCHED",
                    "observed_at": "2026-11-15T12:00:07Z",
                    "processing_job_id": "b2c3d4e5-f6a7-4b8c-9d0e-1f2a3b4c5d6e",
                }
            ]
        }
    )

    id: str = Field(description="Идентификатор наблюдения (UUID строкой)")
    asset_id: str | None = Field(description="Связанный актив (null до разрешения дедупликации)")
    object_type: str = Field(description="Тип объекта по ML", examples=["telecom_well"])
    condition_class: str | None = Field(
        description="Класс состояния по ML", examples=["missing_cover"]
    )
    detector_confidence: float = Field(description="Уверенность детектора 0–1", examples=[0.93])
    review_status: ObservationReviewStatus = Field(description="Статус операторской проверки")
    dedup_result: DeduplicationResult | None = Field(description="Результат дедупликации")
    observed_at: datetime = Field(description="Время наблюдения")
    processing_job_id: str = Field(description="Job, создавший наблюдение")


class RouteMapProperties(BaseModel):
    """Properties слоя /map/routes (геометрия — LineString трека)."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "id": "d4e5f6a7-b8c9-4d0e-1f2a-3b4c5d6e7f80",
                    "name": "Объезд Тверского района, маршрут 1",
                    "vehicle_id": "МГТС-АВ-042",
                    "started_at": "2026-11-15T12:00:00Z",
                    "finished_at": "2026-11-15T13:30:00Z",
                    "total_distance_m": 4321.8,
                }
            ]
        }
    )

    id: str = Field(description="Идентификатор маршрута (UUID строкой)")
    name: str = Field(description="Название маршрута")
    vehicle_id: str | None = Field(description="Идентификатор транспорта")
    started_at: datetime | None = Field(description="Начало объезда")
    finished_at: datetime | None = Field(description="Окончание объезда")
    total_distance_m: float | None = Field(
        description="Длина трека в метрах (PostGIS)", examples=[4321.8]
    )
