"""Frame extraction from images and videos (OpenCV, backend preprocessing only)."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime, timedelta

import cv2
from app.core.exceptions import ValidationAppError
from app.domain.enums import MediaType


@dataclass(frozen=True)
class FrameData:
    index: int
    jpeg_bytes: bytes
    width: int
    height: int
    observed_at: datetime


def probe_frame_count(
    path: str, media_type: MediaType, interval_seconds: float, max_frames: int
) -> int:
    if media_type == MediaType.IMAGE:
        return 1
    capture = cv2.VideoCapture(path)
    try:
        if not capture.isOpened():
            raise ValidationAppError("Cannot open video file (corrupted or unsupported codec)")
        fps = capture.get(cv2.CAP_PROP_FPS) or 25.0
        total = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        if fps <= 0:
            fps = 25.0
        duration = total / fps if total > 0 else 0.0
        estimated = int(duration / interval_seconds) + 1 if duration > 0 else 1
        return max(1, min(estimated, max_frames))
    finally:
        capture.release()


def extract_frames(
    path: str,
    media_type: MediaType,
    *,
    started_at: datetime,
    interval_seconds: float,
    max_frames: int,
) -> Iterator[FrameData]:
    if media_type == MediaType.IMAGE:
        image = cv2.imread(path)
        if image is None:
            raise ValidationAppError("Cannot decode image file (corrupted or unsupported format)")
        height, width = image.shape[:2]
        ok, buffer = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 92])
        if not ok:
            raise ValidationAppError("Failed to encode image")
        yield FrameData(0, buffer.tobytes(), width, height, started_at)
        return

    capture = cv2.VideoCapture(path)
    try:
        if not capture.isOpened():
            raise ValidationAppError("Cannot open video file (corrupted or unsupported codec)")
        fps = capture.get(cv2.CAP_PROP_FPS) or 25.0
        if fps <= 0:
            fps = 25.0
        step = max(1, round(fps * interval_seconds))
        frame_index = 0
        yielded = 0
        while yielded < max_frames:
            ok, image = capture.read()
            if not ok:
                break
            if frame_index % step == 0:
                height, width = image.shape[:2]
                encoded_ok, buffer = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 92])
                if encoded_ok:
                    observed_at = started_at + timedelta(seconds=frame_index / fps)
                    yield FrameData(yielded, buffer.tobytes(), width, height, observed_at)
                    yielded += 1
            frame_index += 1
    finally:
        capture.release()
