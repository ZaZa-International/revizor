"""Privacy filter interface (faces / license plates).

MVP ships a no-op implementation that honestly reports NOT_APPLIED.
The system must never claim anonymization that did not run.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.domain.enums import AnonymizationStatus


@dataclass(frozen=True)
class PrivacyResult:
    status: AnonymizationStatus
    image_bytes: bytes
    error: str | None = None


class PrivacyFilter(Protocol):
    async def process(self, jpeg_bytes: bytes) -> PrivacyResult: ...


class NoopPrivacyFilter:
    """Placeholder: passes frames through and marks them NOT anonymized."""

    async def process(self, jpeg_bytes: bytes) -> PrivacyResult:
        return PrivacyResult(AnonymizationStatus.NOT_APPLIED, jpeg_bytes)
