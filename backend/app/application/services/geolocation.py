"""Geolocation of frames from GPS track metadata.

No fabricated coordinates: without GPS data the result is UNAVAILABLE.
Extension points (map matching, visual localization) plug into this service.

Timestamp policy (GEO-1): device exports frequently carry naive ISO timestamps
(no Z / offset). Naive timestamps are normalized to UTC (assume-UTC policy) so
mixed naive/aware tracks never raise and never silently shift coordinates.
"""

from __future__ import annotations

import math
from bisect import bisect_left
from dataclasses import dataclass
from datetime import UTC, datetime

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


def _normalize_utc(ts: datetime) -> datetime:
    return ts.replace(tzinfo=UTC) if ts.tzinfo is None else ts


def _optional_measure(item: dict, key: str) -> tuple[float | None, bool]:
    raw = item.get(key)
    if raw is None:
        return None, True
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None, False
    if not math.isfinite(value):
        return None, False
    if key == "accuracy_m" and value < 0:
        return None, False
    if key == "heading_deg" and not (0 <= value < 360):
        return None, False
    if key == "speed_mps" and value < 0:
        return None, False
    return value, True


def parse_track(raw: object) -> tuple[list[TrackPoint], int]:
    """Parse upload.metadata['gps_track']; invalid points are counted, not used.

    Naive timestamps are assumed UTC. Non-finite or out-of-range
    accuracy_m / heading_deg / speed_mps invalidate the whole point.
    """
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
        accuracy_m, accuracy_ok = _optional_measure(item, "accuracy_m")
        heading_deg, heading_ok = _optional_measure(item, "heading_deg")
        speed_mps, speed_ok = _optional_measure(item, "speed_mps")
        if not (accuracy_ok and heading_ok and speed_ok):
            invalid += 1
            continue
        points.append(
            TrackPoint(
                timestamp=_normalize_utc(ts),
                point=point,
                accuracy_m=accuracy_m,
                heading_deg=heading_deg,
                speed_mps=speed_mps,
            )
        )
    points.sort(key=lambda p: p.timestamp)
    return points, invalid


class GeolocationService:
    def __init__(
        self,
        track: list[TrackPoint],
        invalid_points: int = 0,
        *,
        gps_max_accuracy_m: float = 50.0,
    ) -> None:
        self._track = track
        self._timestamps = [p.timestamp for p in track]
        self.invalid_points = invalid_points
        self._gps_max_accuracy_m = gps_max_accuracy_m

    @classmethod
    def from_metadata(cls, metadata: dict, gps_max_accuracy_m: float = 50.0) -> GeolocationService:
        track, invalid = parse_track(metadata.get("gps_track"))
        return cls(track, invalid, gps_max_accuracy_m=gps_max_accuracy_m)

    def _nearest(self, observed_at: datetime) -> TrackPoint:
        idx = bisect_left(self._timestamps, observed_at)
        neighbors = [self._track[i] for i in (idx - 1, idx) if 0 <= i < len(self._track)]
        return min(neighbors, key=lambda p: abs((p.timestamp - observed_at).total_seconds()))

    def locate(self, observed_at: datetime) -> GeoObservation:
        observed_at = _normalize_utc(observed_at)
        if not self._track:
            return GeoObservation(
                status=GeolocationStatus.UNAVAILABLE,
                source=GeolocationSource.UNKNOWN,
                observed_at=observed_at,
                invalid_reason="no_gps_track",
            )
        nearest = self._nearest(observed_at)
        gap = abs((nearest.timestamp - observed_at).total_seconds())
        if gap <= CONFIRMED_MAX_GAP_S:
            if nearest.accuracy_m is not None and nearest.accuracy_m > self._gps_max_accuracy_m:
                return GeoObservation(
                    status=GeolocationStatus.ESTIMATED,
                    point=nearest.point,
                    accuracy_m=nearest.accuracy_m,
                    heading_deg=nearest.heading_deg,
                    speed_mps=nearest.speed_mps,
                    source=GeolocationSource.GPS,
                    confidence=0.7,
                    observed_at=observed_at,
                )
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
            idx = bisect_left(self._timestamps, observed_at)
            before = self._track[idx - 1] if idx > 0 else None
            after = self._track[idx] if idx < len(self._track) else None
            if before is not None and after is not None:
                span = (after.timestamp - before.timestamp).total_seconds()
                ratio = (observed_at - before.timestamp).total_seconds() / span if span > 0 else 0.0
                lon = before.point.longitude + ratio * (
                    after.point.longitude - before.point.longitude
                )
                lat = before.point.latitude + ratio * (after.point.latitude - before.point.latitude)
                return GeoObservation(
                    status=GeolocationStatus.ESTIMATED,
                    point=GeoPoint(lon, lat),
                    accuracy_m=max(before.accuracy_m or 10.0, after.accuracy_m or 10.0),
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
