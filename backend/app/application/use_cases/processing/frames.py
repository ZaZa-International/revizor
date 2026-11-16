"""Frame extraction from images and videos (OpenCV, backend preprocessing only).

Dimension safety (SEC-5): image/video dimensions are probed from container
headers BEFORE any pixel decode, so a crafted multi-gigapixel file is rejected
without allocating memory. Frames are downscaled to processing_max_frame_side
for processing only; the original upload in storage is never modified.
"""

from __future__ import annotations

import struct
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import BinaryIO

import cv2
import numpy as np
from app.config import Settings
from app.core.exceptions import ValidationAppError
from app.domain.enums import MediaType

_JPEG_SOF_MARKERS = frozenset({0xC0, 0xC1, 0xC2, 0xC3})
_JPEG_STANDALONE_MARKERS = frozenset({0x01, 0xD8, 0xD9, *range(0xD0, 0xD8)})


@dataclass(frozen=True)
class FrameData:
    index: int
    jpeg_bytes: bytes
    width: int
    height: int
    observed_at: datetime
    original_width: int | None = None
    original_height: int | None = None


def _jpeg_dimensions(fh: BinaryIO) -> tuple[int, int] | None:
    """Walk JPEG segments to the first SOF marker; return (width, height)."""
    while True:
        byte = fh.read(1)
        if not byte:
            return None
        if byte != b"\xff":
            continue
        marker_bytes = fh.read(1)
        while marker_bytes == b"\xff":
            marker_bytes = fh.read(1)
        if not marker_bytes:
            return None
        marker = marker_bytes[0]
        if marker in _JPEG_STANDALONE_MARKERS:
            continue
        if marker == 0xDA:
            return None
        length_bytes = fh.read(2)
        if len(length_bytes) < 2:
            return None
        length = struct.unpack(">H", length_bytes)[0]
        if length < 2:
            return None
        if marker in _JPEG_SOF_MARKERS:
            payload = fh.read(5)
            if len(payload) < 5:
                return None
            height, width = struct.unpack(">HH", payload[1:5])
            return width, height
        fh.seek(length - 2, 1)


def _webp_dimensions(fh: BinaryIO) -> tuple[int, int] | None:
    header = fh.read(12)
    if len(header) < 12 or header[:4] != b"RIFF" or header[8:12] != b"WEBP":
        return None
    while True:
        chunk_header = fh.read(8)
        if len(chunk_header) < 8:
            return None
        fourcc = chunk_header[:4]
        size = struct.unpack("<I", chunk_header[4:8])[0]
        if fourcc == b"VP8X":
            payload = fh.read(10)
            if len(payload) < 10:
                return None
            width = int.from_bytes(payload[4:7], "little") + 1
            height = int.from_bytes(payload[7:10], "little") + 1
            return width, height
        if fourcc == b"VP8 ":
            payload = fh.read(min(size, 10))
            if len(payload) >= 10 and payload[3:6] == b"\x9d\x01\x2a":
                width = struct.unpack("<H", payload[6:8])[0] & 0x3FFF
                height = struct.unpack("<H", payload[8:10])[0] & 0x3FFF
                return width, height
            return None
        if fourcc == b"VP8L":
            payload = fh.read(min(size, 5))
            if len(payload) >= 5 and payload[0] == 0x2F:
                bits = struct.unpack("<I", payload[1:5])[0]
                return (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
            return None
        fh.seek(size + (size % 2), 1)


def probe_image_dimensions(path: str) -> tuple[int, int] | None:
    """Cheap (width, height) probe from JPEG/PNG/WEBP headers, no pixel decode.

    Returns None when the container is not recognized; the caller then falls
    back to decode-time failure handling.
    """
    with open(path, "rb") as fh:
        signature = fh.read(2)
        if signature == b"\xff\xd8":
            return _jpeg_dimensions(fh)
        if signature == b"\x89P":
            fh.seek(0)
            header = fh.read(24)
            if len(header) >= 24 and header[12:16] == b"IHDR":
                width, height = struct.unpack(">II", header[16:24])
                return width, height
            return None
        if signature == b"RI":
            fh.seek(0)
            return _webp_dimensions(fh)
    return None


def validate_dimensions(width: int, height: int, settings: Settings) -> None:
    if width <= 0 or height <= 0:
        return
    if (
        max(width, height) > settings.processing_hard_max_frame_side
        or width * height > settings.processing_max_image_pixels
    ):
        raise ValidationAppError("image_dimensions_exceeded")


def downscale_image(image: np.ndarray, max_side: int) -> np.ndarray:
    height, width = image.shape[:2]
    longest = max(width, height)
    if longest <= max_side:
        return image
    scale = max_side / longest
    new_size = (max(1, round(width * scale)), max(1, round(height * scale)))
    return cv2.resize(image, new_size, interpolation=cv2.INTER_AREA)


def probe_frame_count(
    path: str,
    media_type: MediaType,
    interval_seconds: float,
    max_frames: int,
    settings: Settings | None = None,
) -> int:
    if media_type == MediaType.IMAGE:
        if settings is not None:
            dimensions = probe_image_dimensions(path)
            if dimensions is not None:
                validate_dimensions(*dimensions, settings)
        return 1
    capture = cv2.VideoCapture(path)
    try:
        if not capture.isOpened():
            raise ValidationAppError("Cannot open video file (corrupted or unsupported codec)")
        if settings is not None:
            width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
            height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
            validate_dimensions(width, height, settings)
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
    settings: Settings | None = None,
) -> Iterator[FrameData]:
    if media_type == MediaType.IMAGE:
        if settings is not None:
            dimensions = probe_image_dimensions(path)
            if dimensions is not None:
                validate_dimensions(*dimensions, settings)
        image = cv2.imread(path)
        if image is None:
            raise ValidationAppError("Cannot decode image file (corrupted or unsupported format)")
        original_height, original_width = image.shape[:2]
        if settings is not None:
            image = downscale_image(image, settings.processing_max_frame_side)
        height, width = image.shape[:2]
        ok, buffer = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 92])
        if not ok:
            raise ValidationAppError("Failed to encode image")
        yield FrameData(
            0, buffer.tobytes(), width, height, started_at, original_width, original_height
        )
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
                original_height, original_width = image.shape[:2]
                if settings is not None:
                    image = downscale_image(image, settings.processing_max_frame_side)
                height, width = image.shape[:2]
                encoded_ok, buffer = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 92])
                if encoded_ok:
                    observed_at = started_at + timedelta(seconds=frame_index / fps)
                    yield FrameData(
                        yielded,
                        buffer.tobytes(),
                        width,
                        height,
                        observed_at,
                        original_width,
                        original_height,
                    )
                    yielded += 1
            frame_index += 1
    finally:
        capture.release()
