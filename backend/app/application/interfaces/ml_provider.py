"""MLProvider interface: the only coupling point between backend and ML.

Implementations: MockMLProvider (demo/tests), HTTPMLProvider (external service).
Errors are raised as app.core.exceptions.MLProviderError subclasses:
- MLTimeoutError: request timed out (retryable)
- MLUnavailableError: service unreachable / 5xx (retryable)
- MLContractError: invalid payload or schema_version mismatch (NOT retryable)
- MLInferenceError: model-side inference failure reported by the service
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.schemas.ml import (
    MLBatchResponse,
    MLHealth,
    MLInferenceRequest,
    MLInferenceResponse,
    MLModelInfo,
)


@runtime_checkable
class MLProvider(Protocol):
    name: str

    async def health(self) -> MLHealth: ...

    async def model_info(self) -> MLModelInfo: ...

    async def infer_image(self, request: MLInferenceRequest) -> MLInferenceResponse: ...

    async def infer_batch(self, requests: list[MLInferenceRequest]) -> MLBatchResponse: ...

    async def close(self) -> None: ...
