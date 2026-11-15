"""HTTP client for the external ML inference service (contract schema_version 1.0).

Retry policy: 1 + settings.ml_http_retries attempts on timeouts, connection
errors and HTTP 5xx, with exponential backoff plus jitter. 4xx responses are
never retried. All failures surface as app.core.exceptions.MLProviderError
subclasses. Payloads containing image data and secrets are never logged.
"""

from __future__ import annotations

import asyncio
import random
import time
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from app.config import Settings
from app.core.exceptions import (
    MLContractError,
    MLInferenceError,
    MLProviderError,
    MLTimeoutError,
    MLUnavailableError,
)
from app.core.logging import get_logger
from app.core.metrics import ML_ERRORS, ML_LATENCY
from app.schemas.ml import (
    ML_SCHEMA_VERSION,
    MLBatchResponse,
    MLHealth,
    MLInferenceRequest,
    MLInferenceResponse,
    MLModelInfo,
)

logger = get_logger(__name__)

_ModelT = TypeVar("_ModelT", bound=BaseModel)
_JITTER = random.SystemRandom()


def _validation_summary(exc: ValidationError) -> str:
    parts = [
        f"{'.'.join(str(loc) for loc in err['loc'])}: {err['msg']}" for err in exc.errors()[:3]
    ]
    return "; ".join(parts)


class HTTPMLProvider:
    """MLProvider implementation backed by an external HTTP ML service."""

    name = "http"

    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None) -> None:
        self._settings = settings
        self._owns_client = client is None
        self._client = (
            client
            if client is not None
            else httpx.AsyncClient(
                base_url=settings.ml_http_base_url,
                timeout=settings.ml_http_timeout_seconds,
            )
        )

    async def health(self) -> MLHealth:
        start = time.perf_counter()
        try:
            response = await self._request("GET", "/v1/health", op="health")
            self._raise_for_status(response)
            return self._parse(response, MLHealth, op="health")
        except MLProviderError as exc:
            self._record_error("health", exc)
            raise
        finally:
            ML_LATENCY.labels(self.name, "health").observe(time.perf_counter() - start)

    async def model_info(self) -> MLModelInfo:
        start = time.perf_counter()
        try:
            response = await self._request("GET", "/v1/model-info", op="model_info")
            self._raise_for_status(response)
            return self._parse(response, MLModelInfo, op="model_info")
        except MLProviderError as exc:
            self._record_error("model_info", exc)
            raise
        finally:
            ML_LATENCY.labels(self.name, "model_info").observe(time.perf_counter() - start)

    async def infer_image(self, request: MLInferenceRequest) -> MLInferenceResponse:
        start = time.perf_counter()
        try:
            response = await self._request(
                "POST",
                "/v1/infer",
                op="infer_image",
                json_body=request.model_dump(mode="json"),
            )
            self._raise_for_status(response)
            result = self._parse(response, MLInferenceResponse, op="infer_image")
            self._check_response(result, request)
            logger.debug(
                "ml_infer_image_ok",
                request_id=str(request.request_id),
                detections=len(result.detections),
            )
            return result
        except MLProviderError as exc:
            self._record_error("infer_image", exc, request_id=str(request.request_id))
            raise
        finally:
            ML_LATENCY.labels(self.name, "infer_image").observe(time.perf_counter() - start)

    async def infer_batch(self, requests: list[MLInferenceRequest]) -> MLBatchResponse:
        start = time.perf_counter()
        try:
            body = {
                "schema_version": ML_SCHEMA_VERSION,
                "requests": [request.model_dump(mode="json") for request in requests],
            }
            response = await self._request(
                "POST", "/v1/infer/batch", op="infer_batch", json_body=body
            )
            self._raise_for_status(response)
            batch = self._parse(response, MLBatchResponse, op="infer_batch")
            by_id = {request.request_id: request for request in requests}
            for item in batch.results:
                request = by_id.get(item.request_id)
                if request is None:
                    raise MLContractError(
                        f"batch item request_id {item.request_id} was not in the batch request"
                    )
                if item.status == "OK" and item.response is not None:
                    self._check_response(item.response, request)
            return batch
        except MLProviderError as exc:
            self._record_error("infer_batch", exc, batch_size=len(requests))
            raise
        finally:
            ML_LATENCY.labels(self.name, "infer_batch").observe(time.perf_counter() - start)

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def _request(
        self,
        method: str,
        url: str,
        *,
        op: str,
        json_body: dict[str, Any] | None = None,
    ) -> httpx.Response:
        attempts = 1 + self._settings.ml_http_retries
        reason = "unavailable"
        for attempt in range(attempts):
            try:
                response = await self._client.request(method, url, json=json_body)
            except httpx.TimeoutException:
                reason = "timeout"
            except httpx.ConnectError:
                reason = "connect_error"
            except httpx.TransportError as exc:
                raise MLUnavailableError(f"ML service transport failure: {exc}") from exc
            else:
                if response.status_code < 500:
                    return response
                reason = f"http_{response.status_code}"
            if attempt + 1 < attempts:
                delay = self._settings.ml_http_backoff_seconds * 2**attempt + _JITTER.uniform(
                    0.0, 0.1
                )
                logger.warning(
                    "ml_request_retry",
                    operation=op,
                    attempt=attempt + 1,
                    attempts=attempts,
                    reason=reason,
                    delay_seconds=round(delay, 4),
                )
                await asyncio.sleep(delay)
        if reason == "timeout":
            raise MLTimeoutError(f"ML service timed out after {attempts} attempt(s)")
        raise MLUnavailableError(f"ML service unavailable after {attempts} attempt(s) ({reason})")

    def _raise_for_status(self, response: httpx.Response) -> None:
        if response.status_code < 400:
            return
        code: str | None = None
        message: str | None = None
        try:
            body = response.json()
        except ValueError:
            body = None
        if isinstance(body, dict):
            error = body.get("error")
            if isinstance(error, dict):
                raw_code = error.get("code")
                raw_message = error.get("message")
                code = raw_code if isinstance(raw_code, str) else None
                message = raw_message if isinstance(raw_message, str) else None
        if code == "inference_failed":
            raise MLInferenceError(message or "ML service reported an inference failure")
        detail = f" ({code})" if code else ""
        raise MLContractError(f"ML service returned HTTP {response.status_code}{detail}")

    def _parse(self, response: httpx.Response, model: type[_ModelT], *, op: str) -> _ModelT:
        try:
            payload = response.json()
        except ValueError as exc:
            raise MLContractError(f"ML service returned invalid JSON for {op}") from exc
        try:
            return model.model_validate(payload)
        except ValidationError as exc:
            raise MLContractError(
                f"ML {op} response violates contract {ML_SCHEMA_VERSION}: "
                f"{_validation_summary(exc)}"
            ) from exc

    def _check_response(self, result: MLInferenceResponse, request: MLInferenceRequest) -> None:
        if result.request_id != request.request_id:
            raise MLContractError(
                f"ML response request_id {result.request_id} does not match "
                f"request {request.request_id}"
            )
        for detection in result.detections:
            bbox = detection.bbox
            if not (
                0 <= bbox.x_min < bbox.x_max <= request.image.width
                and 0 <= bbox.y_min < bbox.y_max <= request.image.height
            ):
                raise MLContractError(
                    f"detection {detection.detection_id} bbox is outside image "
                    f"{request.image.width}x{request.image.height}"
                )

    def _record_error(self, op: str, exc: MLProviderError, **context: Any) -> None:
        ML_ERRORS.labels(self.name, exc.code).inc()
        logger.warning("ml_operation_failed", operation=op, code=exc.code, **context)
