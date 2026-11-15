"""Deterministic mock ML provider for demo and testing.

Synthetic detections are seeded by request_id: the same request always yields
the same result. Roughly 15% of requests produce zero detections so that
empty-result behavior stays testable. Image content is never read or logged.
"""

from __future__ import annotations

import asyncio
import random
import time
import uuid

from app.core.exceptions import MLProviderError
from app.core.logging import get_logger
from app.core.metrics import ML_LATENCY
from app.domain.assets.taxonomy import all_asset_types
from app.domain.observations.condition import (
    CANONICAL_CONDITIONS,
    default_severity_for_condition,
)
from app.schemas.ml import (
    ML_SCHEMA_VERSION,
    MLBatchItemResult,
    MLBatchResponse,
    MLBBox,
    MLDetection,
    MLHealth,
    MLInferenceRequest,
    MLInferenceResponse,
    MLItemError,
    MLModelInfo,
)

logger = get_logger(__name__)

_OBJECT_TYPES: tuple[str, ...] = tuple(sorted(t.code for t in all_asset_types()))
_CONDITIONS: tuple[str, ...] = tuple(sorted(CANONICAL_CONDITIONS))
_EMPTY_PROBABILITY = 0.15
_NO_SEVERITY_CONDITIONS = frozenset({"ok", "unknown"})


class MockMLProvider:
    """MLProvider implementation producing synthetic, reproducible detections."""

    name = "mock"

    async def health(self) -> MLHealth:
        return MLHealth(
            status="ok",
            model_loaded=True,
            provider=self.name,
            details={"note": "synthetic detections for demo/testing only"},
        )

    async def model_info(self) -> MLModelInfo:
        return MLModelInfo(
            name="mock-infrastructure-detector",
            version="0.1.0-mock",
            schema_version=ML_SCHEMA_VERSION,
        )

    async def infer_image(self, request: MLInferenceRequest) -> MLInferenceResponse:
        start = time.perf_counter()
        try:
            await asyncio.sleep(0.005)
            rng = random.Random(str(request.request_id))
            count = 0 if rng.random() < _EMPTY_PROBABILITY else rng.randint(1, 3)
            detections = [self._detection(rng, request) for _ in range(count)]
            logger.debug(
                "mock_inference",
                request_id=str(request.request_id),
                detections=len(detections),
            )
            return MLInferenceResponse(
                request_id=request.request_id,
                model=await self.model_info(),
                detections=detections,
                inference_time_ms=round((time.perf_counter() - start) * 1000, 3),
            )
        finally:
            ML_LATENCY.labels(self.name, "infer_image").observe(time.perf_counter() - start)

    async def infer_batch(self, requests: list[MLInferenceRequest]) -> MLBatchResponse:
        results: list[MLBatchItemResult] = []
        for request in requests:
            try:
                response = await self.infer_image(request)
            except MLProviderError as exc:
                results.append(
                    MLBatchItemResult(
                        request_id=request.request_id,
                        status="ERROR",
                        error=MLItemError(code=exc.code, message=exc.message),
                    )
                )
            except Exception as exc:
                results.append(
                    MLBatchItemResult(
                        request_id=request.request_id,
                        status="ERROR",
                        error=MLItemError(code="inference_failed", message=str(exc)),
                    )
                )
            else:
                results.append(
                    MLBatchItemResult(request_id=request.request_id, status="OK", response=response)
                )
        return MLBatchResponse(model=await self.model_info(), results=results)

    async def close(self) -> None:
        return None

    def _detection(self, rng: random.Random, request: MLInferenceRequest) -> MLDetection:
        condition = rng.choice(_CONDITIONS)
        width = request.image.width
        height = request.image.height
        severity = (
            None
            if condition in _NO_SEVERITY_CONDITIONS
            else default_severity_for_condition(condition)
        )
        return MLDetection(
            detection_id=uuid.UUID(int=rng.getrandbits(128), version=4),
            object_type=rng.choice(_OBJECT_TYPES),
            condition_class=condition,
            confidence=round(rng.uniform(0.55, 0.97), 4),
            severity=severity,
            bbox=MLBBox(
                x_min=round(rng.uniform(0.02 * width, 0.4 * width), 2),
                y_min=round(rng.uniform(0.02 * height, 0.4 * height), 2),
                x_max=round(rng.uniform(0.6 * width, 0.98 * width), 2),
                y_max=round(rng.uniform(0.6 * height, 0.98 * height), 2),
            ),
            embedding=None,
            attributes={"mock": True},
        )
