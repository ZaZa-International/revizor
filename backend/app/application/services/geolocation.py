"""Geolocation of frames from GPS track metadata.

No fabricated coordinates: without GPS data the result is UNAVAILABLE.
Extension points (map matching, visual localization) plug into this service.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.domain.enums import GeolocationSource, GeolocationStatus
from app.domain.geospatial.models import CoordinateError, GeoObservation, GeoPoint


@dataclass(frozen=True)
class TrackPoint:
    timestamp: datetime
    point: GeoPoint
    accuracy_m: float | None = None
    heading_deg: float | None = None
    speed_mps: float | None = None


CONFIRMED_MAX_GAP_S = 2.0
INTERPOLATED_MAX_GAP_S = 10.0


def parse_track(raw: object) -> tuple[list[TrackPoint], int]:
    """Parse upload.metadata['gps_track']; invalid points are counted, not used."""
    points: list[TrackPoint] = []
    invalid = 0
    if not isinstance(raw, list):
        return points, invalid
    for item in raw:
        if not isinstance(item, dict):
            invalid += 1
            continue
        try:
            ts = datetime.fromisoformat(str(item["timestamp"]).replace("Z", "+00:00"))
            point = GeoPoint(float(item["longitude"]), float(item["latitude"]))
        except (KeyError, TypeError, ValueError, CoordinateError):
            invalid += 1
            continue
        points.append(
            TrackPoint(
                timestamp=ts,
                point=point,
                accuracy_m=float(item["accuracy_m"])
                if item.get("accuracy_m") is not None
                else None,
                heading_deg=float(item["heading_deg"])
                if item.get("heading_deg") is not None
                else None,
                speed_mps=float(item["speed_mps"]) if item.get("speed_mps") is not None else None,
            )
        )
    points.sort(key=lambda p: p.timestamp)
    return points, invalid


class GeolocationService:
    def __init__(self, track: list[TrackPoint], invalid_points: int = 0) -> None:
        self._track = track
        self.invalid_points = invalid_points

    @classmethod
    def from_metadata(cls, metadata: dict) -> GeolocationService:
        track, invalid = parse_track(metadata.get("gps_track"))
        return cls(track, invalid)

    def locate(self, observed_at: datetime) -> GeoObservation:
        if not self._track:
            return GeoObservation(
                status=GeolocationStatus.UNAVAILABLE,
                source=GeolocationSource.UNKNOWN,
                observed_at=observed_at,
                invalid_reason="no_gps_track",
            )
        nearest = min(self._track, key=lambda p: abs((p.timestamp - observed_at).total_seconds()))
        gap = abs((nearest.timestamp - observed_at).total_seconds())
        if gap <= CONFIRMED_MAX_GAP_S:
            return GeoObservation(
                status=GeolocationStatus.CONFIRMED,
                point=nearest.point,
                accuracy_m=nearest.accuracy_m,
                heading_deg=nearest.heading_deg,
                speed_mps=nearest.speed_mps,
                source=GeolocationSource.GPS,
                confidence=1.0,
                observed_at=observed_at,
            )
        if gap <= INTERPOLATED_MAX_GAP_S:
            before = [p for p in self._track if p.timestamp <= observed_at]
            after = [p for p in self._track if p.timestamp >= observed_at]
            if before and after:
                p0, p1 = before[-1], after[0]
                span = (p1.timestamp - p0.timestamp).total_seconds()
                ratio = (observed_at - p0.timestamp).total_seconds() / span if span > 0 else 0.0
                lon = p0.point.longitude + ratio * (p1.point.longitude - p0.point.longitude)
                lat = p0.point.latitude + ratio * (p1.point.latitude - p0.point.latitude)
                return GeoObservation(
                    status=GeolocationStatus.ESTIMATED,
                    point=GeoPoint(lon, lat),
                    accuracy_m=max(p0.accuracy_m or 10.0, p1.accuracy_m or 10.0),
                    source=GeolocationSource.GPS,
                    confidence=0.6,
                    observed_at=observed_at,
                )
            return GeoObservation(
                status=GeolocationStatus.ESTIMATED,
                point=nearest.point,
                accuracy_m=(nearest.accuracy_m or 5.0) + gap,
                source=GeolocationSource.GPS,
                confidence=0.4,
                observed_at=observed_at,
            )
        return GeoObservation(
            status=GeolocationStatus.UNAVAILABLE,
            source=GeolocationSource.UNKNOWN,
            observed_at=observed_at,
            invalid_reason=f"gps_gap_too_large:{gap:.0f}s",
        )
