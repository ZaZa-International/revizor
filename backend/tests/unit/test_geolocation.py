from datetime import UTC, datetime, timedelta

import pytest
from app.application.services.geolocation import GeolocationService, parse_track
from app.domain.enums import GeolocationStatus
from app.domain.geospatial.models import CoordinateError, GeoPoint

from tests.fixtures.media import gps_track

pytestmark = pytest.mark.unit

START = datetime(2026, 11, 15, 12, 0, 0, tzinfo=UTC)


def test_parse_track_valid():
    track, invalid = parse_track(gps_track(START, points=5))
    assert len(track) == 5
    assert invalid == 0
    assert track[0].point.longitude == pytest.approx(37.6173)


def test_parse_track_skips_invalid_points():
    raw = gps_track(START, points=3)
    raw.append({"timestamp": "bad", "longitude": 1, "latitude": 2})
    raw.append({"timestamp": START.isoformat(), "longitude": 200.0, "latitude": 55.0})
    raw.append({"timestamp": START.isoformat(), "longitude": 37.0, "latitude": 95.0})
    raw.append("not-a-dict")
    track, invalid = parse_track(raw)
    assert len(track) == 3
    assert invalid == 4


def test_no_track_means_unavailable():
    service = GeolocationService.from_metadata({})
    result = service.locate(START)
    assert result.status == GeolocationStatus.UNAVAILABLE
    assert result.point is None
    assert result.invalid_reason == "no_gps_track"


def test_exact_timestamp_confirmed():
    service = GeolocationService.from_metadata({"gps_track": gps_track(START, points=5)})
    result = service.locate(START + timedelta(seconds=2))
    assert result.status == GeolocationStatus.CONFIRMED
    assert result.point is not None
    assert result.accuracy_m == 4.0


def test_small_gap_interpolated_estimated():
    track = [
        {
            "timestamp": START.isoformat(),
            "longitude": 37.6173,
            "latitude": 55.7558,
            "accuracy_m": 4.0,
        },
        {
            "timestamp": (START + timedelta(seconds=8)).isoformat(),
            "longitude": 37.6183,
            "latitude": 55.7568,
            "accuracy_m": 4.0,
        },
    ]
    service = GeolocationService.from_metadata({"gps_track": track})
    result = service.locate(START + timedelta(seconds=4))
    assert result.status == GeolocationStatus.ESTIMATED
    assert result.point is not None
    assert result.point.longitude == pytest.approx(37.6178, abs=1e-6)


def test_large_gap_unavailable():
    service = GeolocationService.from_metadata({"gps_track": gps_track(START, points=2)})
    result = service.locate(START + timedelta(hours=1))
    assert result.status == GeolocationStatus.UNAVAILABLE
    assert result.point is None


def test_swapped_coordinates_detected_when_out_of_range():
    point = GeoPoint(longitude=55.75, latitude=37.61)
    assert point.latitude == 37.61
    with pytest.raises(CoordinateError) as exc:
        GeoPoint(longitude=55.75, latitude=137.61)
    assert "swapped" in (exc.value.hint or "")
    with pytest.raises(CoordinateError):
        GeoPoint(longitude=200.0, latitude=55.0)


def test_geopoint_wkt_order_lon_lat():
    point = GeoPoint(longitude=37.6173, latitude=55.7558)
    assert point.to_wkt() == "POINT(37.6173 55.7558)"
    assert point.to_geojson()["coordinates"] == [37.6173, 55.7558]
