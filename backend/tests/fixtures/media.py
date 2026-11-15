"""Synthetic media generation for tests (clearly artificial, no real data)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import cv2
import numpy as np


def make_jpeg_bytes(
    width: int = 640,
    height: int = 480,
    seed: int = 42,
    *,
    quality: str = "good",
) -> bytes:
    rng = np.random.default_rng(seed)
    if quality == "dark":
        image = np.full((height, width, 3), 3, dtype=np.uint8)
    elif quality == "blurry":
        image = np.full((height, width, 3), 120, dtype=np.uint8)
    else:
        image = rng.integers(0, 255, (height, width, 3), dtype=np.uint8)
        for _ in range(12):
            x0, y0 = int(rng.integers(0, width - 60)), int(rng.integers(0, height - 60))
            color = tuple(int(c) for c in rng.integers(0, 255, 3))
            cv2.rectangle(image, (x0, y0), (x0 + 50, y0 + 50), color, 2)
        cv2.putText(
            image, f"SYNTHETIC-{seed}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2
        )
    ok, buffer = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 92])
    assert ok
    return buffer.tobytes()


def make_video_file(
    path: str,
    *,
    frames: int = 30,
    fps: int = 10,
    width: int = 640,
    height: int = 480,
    bad_frame_indices: tuple[int, ...] = (),
) -> str:
    writer = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"mp4v"), fps, (width, height))
    assert writer.isOpened(), "VideoWriter unavailable (codec support)"
    rng = np.random.default_rng(7)
    for index in range(frames):
        if index in bad_frame_indices:
            frame = np.full((height, width, 3), 2, dtype=np.uint8)
        else:
            frame = rng.integers(0, 255, (height, width, 3), dtype=np.uint8)
            cv2.putText(
                frame, f"F{index}", (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 2
            )
        writer.write(frame)
    writer.release()
    return path


def gps_track(
    start: datetime | None = None,
    *,
    points: int = 10,
    start_lon: float = 37.6173,
    start_lat: float = 55.7558,
    step_m: float = 8.0,
) -> list[dict]:
    """Synthetic GPS track near Moscow center; demo/test data only."""
    start = start or datetime(2026, 11, 15, 12, 0, 0, tzinfo=UTC)
    track = []
    lat_step = step_m / 111_320.0
    lon_step = step_m / (111_320.0 * 0.56)
    for i in range(points):
        track.append(
            {
                "timestamp": (start + timedelta(seconds=i)).isoformat(),
                "longitude": round(start_lon + i * lon_step, 7),
                "latitude": round(start_lat + i * lat_step, 7),
                "accuracy_m": 4.0,
                "heading_deg": 45.0,
                "speed_mps": step_m,
            }
        )
    return track


def upload_metadata(start: datetime | None = None, *, with_gps: bool = True) -> dict:
    start = start or datetime(2026, 11, 15, 12, 0, 0, tzinfo=UTC)
    metadata: dict = {"capture_started_at": start.isoformat(), "demo": True}
    if with_gps:
        metadata["gps_track"] = gps_track(start)
    return metadata
