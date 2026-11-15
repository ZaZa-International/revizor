"""Geospatial value objects and coordinate validation.

Coordinate order is ALWAYS (longitude, latitude). Validation detects the
common lat/lon swap instead of silently accepting invalid coordinates.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from app.domain.enums import GeolocationSource, GeolocationStatus


class CoordinateError(ValueError):
    def __init__(self, message: str, hint: str | None = None) -> None:
        super().__init__(message)
        self.hint = hint


def validate_coordinates(longitude: float, latitude: float) -> None:
    if not (-180.0 <= longitude <= 180.0) or not (-90.0 <= latitude <= 90.0):
        if -90.0 <= longitude <= 90.0 and -180.0 <= latitude <= 180.0 and abs(latitude) > 90.0:
            raise CoordinateError(
                f"Invalid coordinates (lon={longitude}, lat={latitude})",
                hint="coordinates_appear_swapped: expected (longitude, latitude)",
            )
        raise CoordinateError(f"Coordinates out of range (lon={longitude}, lat={latitude})")


@dataclass(frozen=True)
class GeoPoint:
    longitude: float
    latitude: float

    def __post_init__(self) -> None:
        validate_coordinates(self.longitude, self.latitude)

    def to_wkt(self) -> str:
        return f"POINT({self.longitude} {self.latitude})"

    def to_geojson(self) -> dict[str, object]:
        return {"type": "Point", "coordinates": [self.longitude, self.latitude]}


@dataclass(frozen=True)
class GeoObservation:
    """Geolocation attached to an observation/frame, incl. quality metadata."""

    status: GeolocationStatus
    point: GeoPoint | None = None
    accuracy_m: float | None = None
    heading_deg: float | None = None
    speed_mps: float | None = None
    source: GeolocationSource = GeolocationSource.UNKNOWN
    confidence: float | None = None
    observed_at: datetime | None = None
    invalid_reason: str | None = None

    def __post_init__(self) -> None:
        if (
            self.status in (GeolocationStatus.CONFIRMED, GeolocationStatus.ESTIMATED)
            and self.point is None
        ):
            raise ValueError("Confirmed/estimated geolocation requires a point")
        if (
            self.status in (GeolocationStatus.UNAVAILABLE, GeolocationStatus.INVALID)
            and self.point is not None
        ):
            raise ValueError("Unavailable/invalid geolocation must not carry a point")


@dataclass(frozen=True)
class BoundingBox:
    """Geographic bounding box in WGS84 degrees: (min_lon, min_lat, max_lon, max_lat)."""

    min_lon: float
    min_lat: float
    max_lon: float
    max_lat: float

    def __post_init__(self) -> None:
        validate_coordinates(self.min_lon, self.min_lat)
        validate_coordinates(self.max_lon, self.max_lat)
        if self.min_lon > self.max_lon or self.min_lat > self.max_lat:
            raise CoordinateError("Bounding box min must not exceed max")

    @classmethod
    def parse(cls, raw: str) -> BoundingBox:
        parts = [p.strip() for p in raw.split(",")]
        if len(parts) != 4:
            raise CoordinateError("bbox must be 'min_lon,min_lat,max_lon,max_lat'")
        try:
            values = [float(p) for p in parts]
        except ValueError as exc:
            raise CoordinateError("bbox values must be numeric") from exc
        return cls(*values)

    def to_wkt_polygon(self) -> str:
        return (
            f"POLYGON(({self.min_lon} {self.min_lat}, {self.max_lon} {self.min_lat}, "
            f"{self.max_lon} {self.max_lat}, {self.min_lon} {self.max_lat}, "
            f"{self.min_lon} {self.min_lat}))"
        )


@dataclass(frozen=True)
class PixelBBox:
    x_min: float
    y_min: float
    x_max: float
    y_max: float

    def validate(self, width: int, height: int) -> None:
        if not (0 <= self.x_min < self.x_max <= width and 0 <= self.y_min < self.y_max <= height):
            raise CoordinateError(
                f"Pixel bbox ({self.x_min},{self.y_min},{self.x_max},{self.y_max}) "
                f"outside image bounds {width}x{height}"
            )

    def to_dict(self) -> dict[str, float]:
        return {
            "x_min": self.x_min,
            "y_min": self.y_min,
            "x_max": self.x_max,
            "y_max": self.y_max,
        }


@dataclass
class GeoSearchFilters:
    bbox: BoundingBox | None = None
    center: GeoPoint | None = None
    radius_m: float | None = None
    extra: dict[str, object] = field(default_factory=dict)
