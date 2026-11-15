"""Quality gate: transparent OpenCV heuristics for MVP.

The interface allows replacing heuristics with a learned quality model later.
Every rejection records its reason.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

import cv2
import numpy as np
from app.config import Settings
from app.domain.enums import FrameQualityVerdict


@dataclass(frozen=True)
class QualityResult:
    verdict: FrameQualityVerdict
    reasons: list[str] = field(default_factory=list)
    metrics: dict[str, float] = field(default_factory=dict)


class QualityGate(Protocol):
    def evaluate(self, jpeg_bytes: bytes, width: int, height: int) -> QualityResult: ...


class HeuristicQualityGate:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def evaluate(self, jpeg_bytes: bytes, width: int, height: int) -> QualityResult:
        if not self._settings.quality_gate_enabled:
            return QualityResult(FrameQualityVerdict.PASS)
        reasons: list[str] = []
        metrics: dict[str, float] = {}
        if width < self._settings.quality_min_width or height < self._settings.quality_min_height:
            reasons.append("low_resolution")
        image = cv2.imdecode(np.frombuffer(jpeg_bytes, dtype=np.uint8), cv2.IMREAD_GRAYSCALE)
        if image is None:
            return QualityResult(FrameQualityVerdict.REJECT, ["undecodable_frame"], {})
        blur = float(cv2.Laplacian(image, cv2.CV_64F).var())
        brightness = float(image.mean())
        metrics["blur_variance"] = round(blur, 2)
        metrics["brightness_mean"] = round(brightness, 2)
        if blur < self._settings.quality_blur_threshold:
            reasons.append("blur")
        if brightness > self._settings.quality_overexposure_mean:
            reasons.append("overexposure")
        if brightness < self._settings.quality_underexposure_mean:
            reasons.append("underexposure")
        verdict = FrameQualityVerdict.REJECT if reasons else FrameQualityVerdict.PASS
        return QualityResult(verdict, reasons, metrics)
