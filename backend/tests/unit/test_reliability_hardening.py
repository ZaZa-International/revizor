"""Wave-1 reliability hardening unit tests (no external services).

Covers: SEC-5 dimension probes, PERF-2 downscale, GEO-1/3 timestamp/accuracy
policy, REL-1 stale helper, REL-2 transitions, REL-4 deterministic request id,
REL-12 crop keys, GEO-2/SEC-18 presign, ARCH-17 local streaming.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock
from urllib.parse import parse_qs, urlparse

import cv2
import numpy as np
import pytest
from app.application.services.geolocation import GeolocationService, parse_track
from app.application.use_cases.processing.frames import (
    downscale_image,
    extract_frames,
    probe_frame_count,
    probe_image_dimensions,
    validate_dimensions,
)
from app.application.use_cases.processing.pipeline import (
    ProcessingPipeline,
    crop_storage_key,
    frame_request_id,
)
from app.config import Settings
from app.core.exceptions import StorageObjectNotFoundError, ValidationAppError
from app.domain.enums import GeolocationStatus, JobStatus, MediaType
from app.domain.processing.state_machine import (
    assert_transition,
    can_transition,
    is_stale_processing,
)
from app.infrastructure.storage.local import LocalFilesystemStorage
from app.infrastructure.storage.s3 import S3Storage

from tests.fixtures.media import make_jpeg_bytes

pytestmark = pytest.mark.unit

START = datetime(2026, 11, 15, 12, 0, 0, tzinfo=UTC)


def _jpeg_with_sof(width: int, height: int) -> bytes:
    """Minimal JPEG container: SOI + APP0 + SOF0 declaring arbitrary dimensions."""
    sof_payload = (
        b"\x08"
        + height.to_bytes(2, "big")
        + width.to_bytes(2, "big")
        + b"\x03"
        + b"\x01\x11\x00\x02\x11\x01\x03\x11\x01"
    )
    app0_payload = b"JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
    return (
        b"\xff\xd8"
        + b"\xff\xe0"
        + (len(app0_payload) + 2).to_bytes(2, "big")
        + app0_payload
        + b"\xff\xc0"
        + (len(sof_payload) + 2).to_bytes(2, "big")
        + sof_payload
        + b"\xff\xd9"
    )


def test_jpeg_sof_probe_reads_dimensions(tmp_path):
    path = tmp_path / "huge.jpg"
    path.write_bytes(_jpeg_with_sof(30000, 20000))
    assert probe_image_dimensions(str(path)) == (30000, 20000)


def test_oversized_jpeg_rejected_before_decode(tmp_path, settings, monkeypatch):
    path = tmp_path / "bomb.jpg"
    path.write_bytes(_jpeg_with_sof(30000, 30000))

    def _no_decode(*args, **kwargs):
        raise AssertionError("decode must not happen for oversized images")

    monkeypatch.setattr(cv2, "imread", _no_decode)
    monkeypatch.setattr(cv2, "imdecode", _no_decode)
    with pytest.raises(ValidationAppError) as exc:
        probe_frame_count(str(path), MediaType.IMAGE, 1.0, 2000, settings=settings)
    assert exc.value.message == "image_dimensions_exceeded"
    with pytest.raises(ValidationAppError):
        list(
            extract_frames(
                str(path),
                MediaType.IMAGE,
                started_at=START,
                interval_seconds=1.0,
                max_frames=10,
                settings=settings,
            )
        )


def test_pixel_budget_rejected_even_under_side_cap(tmp_path, settings):
    path = tmp_path / "pixels.jpg"
    path.write_bytes(_jpeg_with_sof(8100, 8100))
    assert settings.processing_hard_max_frame_side >= 8100
    assert settings.processing_max_image_pixels < 8100 * 8100
    with pytest.raises(ValidationAppError):
        validate_dimensions(8100, 8100, settings)


def test_png_ihdr_probe(tmp_path):
    import struct

    header = b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR"
    header += struct.pack(">II", 40000, 100) + b"\x08\x02\x00\x00\x00"
    path = tmp_path / "big.png"
    path.write_bytes(header)
    assert probe_image_dimensions(str(path)) == (40000, 100)


def test_webp_vp8l_probe(tmp_path):
    import struct

    width, height = 16000, 10000
    bits = (width - 1) | ((height - 1) << 14)
    payload = b"\x2f" + struct.pack("<I", bits)
    chunk = b"VP8L" + struct.pack("<I", len(payload)) + payload
    body = b"WEBP" + chunk
    path = tmp_path / "big.webp"
    path.write_bytes(b"RIFF" + struct.pack("<I", len(body)) + body)
    assert probe_image_dimensions(str(path)) == (width, height)


def test_downscale_math():
    image = np.zeros((3000, 5000, 3), dtype=np.uint8)
    scaled = downscale_image(image, 4096)
    assert scaled.shape[1] == 4096
    assert scaled.shape[0] == round(3000 * 4096 / 5000)
    small = np.zeros((480, 640, 3), dtype=np.uint8)
    assert downscale_image(small, 4096) is small


def test_extract_frames_downscales_and_keeps_original_dims(tmp_path, settings):
    path = tmp_path / "wide.jpg"
    path.write_bytes(make_jpeg_bytes(width=5000, height=3000, seed=11))
    frames = list(
        extract_frames(
            str(path),
            MediaType.IMAGE,
            started_at=START,
            interval_seconds=1.0,
            max_frames=10,
            settings=settings,
        )
    )
    assert len(frames) == 1
    frame = frames[0]
    assert frame.width == settings.processing_max_frame_side
    assert frame.height == round(3000 * settings.processing_max_frame_side / 5000)
    assert frame.original_width == 5000
    assert frame.original_height == 3000


def test_extract_frames_small_image_not_downscaled(tmp_path, settings):
    path = tmp_path / "small.jpg"
    path.write_bytes(make_jpeg_bytes(width=640, height=480, seed=12))
    frame = next(
        extract_frames(
            str(path),
            MediaType.IMAGE,
            started_at=START,
            interval_seconds=1.0,
            max_frames=10,
            settings=settings,
        )
    )
    assert (frame.width, frame.height) == (640, 480)
    assert (frame.original_width, frame.original_height) == (640, 480)


def _point(ts: datetime, lon: float = 37.6173, lat: float = 55.7558, **extra) -> dict:
    return {"timestamp": ts.isoformat(), "longitude": lon, "latitude": lat, **extra}


def test_naive_track_normalized_to_utc():
    naive = datetime(2026, 11, 15, 12, 0, 0)
    track, invalid = parse_track([_point(naive), _point(naive + timedelta(seconds=1))])
    assert invalid == 0
    assert all(p.timestamp.tzinfo is UTC for p in track)
    service = GeolocationService(track)
    result = service.locate(naive)
    assert result.status == GeolocationStatus.CONFIRMED


def test_mixed_naive_aware_track_sorts_and_locates():
    naive = datetime(2026, 11, 15, 12, 0, 1)
    raw = [_point(START + timedelta(seconds=2)), _point(naive), _point(START)]
    track, invalid = parse_track(raw)
    assert invalid == 0
    assert [p.timestamp for p in track] == sorted(p.timestamp for p in track)
    service = GeolocationService(track)
    assert service.locate(naive).status == GeolocationStatus.CONFIRMED


def test_non_finite_and_out_of_range_measures_invalid_point():
    raw = [
        _point(START, accuracy_m=float("nan")),
        _point(START, accuracy_m=-1.0),
        _point(START, heading_deg=400.0),
        _point(START, speed_mps=-5.0),
        _point(START, accuracy_m=float("inf")),
        _point(START, accuracy_m=4.0, heading_deg=45.0, speed_mps=8.0),
    ]
    track, invalid = parse_track(raw)
    assert invalid == 5
    assert len(track) == 1


def test_accuracy_gate_downgrades_confirmed_to_estimated():
    raw = [_point(START, accuracy_m=1000.0)]
    service = GeolocationService.from_metadata({"gps_track": raw})
    result = service.locate(START)
    assert result.status == GeolocationStatus.ESTIMATED
    assert result.confidence == 0.7
    assert result.accuracy_m == 1000.0


def test_accuracy_none_stays_confirmed():
    service = GeolocationService.from_metadata({"gps_track": [_point(START)]})
    result = service.locate(START)
    assert result.status == GeolocationStatus.CONFIRMED
    assert result.confidence == 1.0


def test_accuracy_gate_threshold_configurable():
    raw = [_point(START, accuracy_m=60.0)]
    strict = GeolocationService.from_metadata({"gps_track": raw}, gps_max_accuracy_m=50.0)
    lenient = GeolocationService.from_metadata({"gps_track": raw}, gps_max_accuracy_m=100.0)
    assert strict.locate(START).status == GeolocationStatus.ESTIMATED
    assert lenient.locate(START).status == GeolocationStatus.CONFIRMED


def test_bisect_nearest_equivalent_to_brute_force():
    track, _ = parse_track(
        [
            _point(START + timedelta(seconds=3 * i), lon=37.6 + i * 0.001, lat=55.7 + i * 0.0005)
            for i in range(50)
        ]
    )
    service = GeolocationService(track)
    probes = [START - timedelta(seconds=7)]
    probes += [START + timedelta(seconds=0.7 * k) for k in range(220)]
    probes += [START + timedelta(seconds=149), START + timedelta(seconds=200)]
    for observed_at in probes:
        brute = min(track, key=lambda p: abs((p.timestamp - observed_at).total_seconds()))
        assert service._nearest(observed_at) == brute


def test_pipeline_resolve_start_normalizes_naive(settings):
    pipeline = ProcessingPipeline(MagicMock(), MagicMock(), MagicMock(), settings)
    resolved = pipeline._resolve_start({"capture_started_at": "2026-11-15T12:00:00"}, START)
    assert resolved.tzinfo is UTC
    assert resolved == START
    aware = pipeline._resolve_start({"capture_started_at": START.isoformat()}, START)
    assert aware == START


def test_stale_processing_helper():
    old = datetime.now(UTC) - timedelta(seconds=3600)
    fresh = datetime.now(UTC) - timedelta(seconds=5)
    assert is_stale_processing(JobStatus.PROCESSING, old, 1920)
    assert not is_stale_processing(JobStatus.PROCESSING, fresh, 1920)
    assert not is_stale_processing(JobStatus.QUEUED, old, 1920)
    assert not is_stale_processing(JobStatus.COMPLETED, old, 1920)
    assert is_stale_processing(JobStatus.PROCESSING, old.replace(tzinfo=None), 1920)


def test_state_machine_resume_and_stale_transitions():
    assert can_transition(JobStatus.PROCESSING, JobStatus.QUEUED)
    assert can_transition(JobStatus.FAILED, JobStatus.PROCESSING)
    assert can_transition(JobStatus.PARTIALLY_COMPLETED, JobStatus.PROCESSING)
    assert_transition(JobStatus.FAILED, JobStatus.PROCESSING)
    assert_transition(JobStatus.PARTIALLY_COMPLETED, JobStatus.PROCESSING)
    for target in JobStatus:
        assert not can_transition(JobStatus.COMPLETED, target)


def test_deterministic_request_id():
    job_id = uuid.uuid4()
    first = frame_request_id(job_id, 7)
    assert first == frame_request_id(job_id, 7)
    assert first != frame_request_id(job_id, 8)
    assert first != frame_request_id(uuid.uuid4(), 7)
    assert first == uuid.uuid5(uuid.NAMESPACE_URL, f"{job_id}:7")


def test_crop_key_format():
    job_id = uuid.UUID("12345678-1234-5678-1234-567812345678")
    assert crop_storage_key(job_id, 3, 2) == f"crops/{job_id}/000003_02.jpg"
    assert crop_storage_key(job_id, 123456, 11) == f"crops/{job_id}/123456_11.jpg"


async def test_s3_presign_uses_public_endpoint_and_settings_expiry():
    settings = Settings(
        storage_backend="s3",
        s3_endpoint_url="http://s3:9000",
        s3_public_endpoint_url="http://public.example:9000",
        s3_presign_expires_seconds=120,
    )
    storage = S3Storage(settings)
    try:
        url = await storage.generate_presigned_url("frames/x.jpg")
        parsed = urlparse(url)
        assert parsed.hostname == "public.example"
        assert parsed.port == 9000
        assert parse_qs(parsed.query)["X-Amz-Expires"] == ["120"]
        short = await storage.generate_presigned_url("frames/x.jpg", expires_seconds=60)
        assert parse_qs(urlparse(short).query)["X-Amz-Expires"] == ["60"]
        with pytest.raises(ValueError):
            await storage.generate_presigned_url("frames/x.jpg", method="PUT")
    finally:
        await storage.close()


async def test_s3_presign_falls_back_to_internal_endpoint():
    settings = Settings(
        storage_backend="s3",
        s3_endpoint_url="http://localhost:9000",
        s3_public_endpoint_url="",
    )
    storage = S3Storage(settings)
    try:
        url = await storage.generate_presigned_url("frames/x.jpg")
        assert urlparse(url).hostname == "localhost"
    finally:
        await storage.close()


async def test_local_streaming_roundtrip(tmp_path):
    storage = LocalFilesystemStorage(str(tmp_path / "store"))
    source = tmp_path / "source.bin"
    payload = bytes(range(256)) * 4096
    source.write_bytes(payload)
    key = "uploads/stream.bin"
    await storage.upload_file(key, str(source), "application/octet-stream")
    target = tmp_path / "target.bin"
    await storage.download_to_file(key, str(target))
    assert target.read_bytes() == payload
    meta = await storage.get_metadata(key)
    assert meta.size == len(payload)
    assert meta.content_type == "application/octet-stream"
    assert meta.checksum_sha256 is None
    with pytest.raises(StorageObjectNotFoundError):
        await storage.download_to_file("missing.bin", str(tmp_path / "out.bin"))
