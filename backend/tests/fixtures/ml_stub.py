"""Deterministic ML stub for pipeline integration tests."""

from __future__ import annotations

import uuid
from collections.abc import Callable

from app.core.exceptions import MLProviderError
from app.schemas.ml import (
    MLBBox,
    MLDetection,
    MLHealth,
    MLInferenceRequest,
    MLInferenceResponse,
    MLModelInfo,
)

NAMESPACE = uuid.UUID("6ba7b811-9dad-11d1-80b4-00c04fd430c8")


def default_detections(request: MLInferenceRequest) -> list[MLDetection]:
    detection_id = uuid.uuid5(NAMESPACE, request.image.storage_key)
    return [
        MLDetection(
            detection_id=detection_id,
            object_type="telecom_well",
            condition_class="damaged_cover",
            confidence=0.92,
            severity=4,
            bbox=MLBBox(x_min=10, y_min=10, x_max=200, y_max=200),
        )
    ]


class StubMLProvider:
    name = "stub"

    def __init__(
        self,
        factory: Callable[[MLInferenceRequest], list[MLDetection]] | None = None,
        fail_with: MLProviderError | None = None,
    ) -> None:
        self._factory = factory or default_detections
        self._fail_with = fail_with
        self.calls = 0

    async def health(self) -> MLHealth:
        return MLHealth(status="ok", model_loaded=True, provider="stub")

    async def model_info(self) -> MLModelInfo:
        return MLModelInfo(name="stub-detector", version="0.0.1-test")

    async def infer_image(self, request: MLInferenceRequest) -> MLInferenceResponse:
        self.calls += 1
        if self._fail_with is not None:
            raise self._fail_with
        return MLInferenceResponse(
            request_id=request.request_id,
            model=await self.model_info(),
            detections=self._factory(request),
        )

    async def infer_batch(self, requests: list[MLInferenceRequest]):
        from app.schemas.ml import MLBatchItemResult, MLBatchResponse

        results = []
        for request in requests:
            response = await self.infer_image(request)
            results.append(
                MLBatchItemResult(request_id=request.request_id, status="OK", response=response)
            )
        return MLBatchResponse(model=await self.model_info(), results=results)

    async def close(self) -> None:
        return None
