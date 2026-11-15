"""Unit tests for MockMLProvider, HTTPMLProvider and the provider factory.

HTTP tests use httpx.MockTransport: no external services are required.
"""

from __future__ import annotations

import json
import random
import uuid
from collections.abc import Callable
from typing import Any

import httpx
import pytest
from app.application.interfaces.ml_provider import MLProvider
from app.config import Settings
from app.core.exceptions import (
    MLContractError,
    MLInferenceError,
    MLTimeoutError,
    MLUnavailableError,
)
from app.core.metrics import REGISTRY
from app.domain.assets.taxonomy import all_asset_types
from app.domain.observations.condition import (
    CANONICAL_CONDITIONS,
    default_severity_for_condition,
)
from app.infrastructure.ml.factory import build_ml_provider
from app.infrastructure.ml.http_provider import HTTPMLProvider
from app.infrastructure.ml.mock_provider import MockMLProvider
from app.schemas.ml import (
    MLBBox,
    MLDetection,
    MLImageRef,
    MLInferenceRequest,
    MLInferenceResponse,
    MLModelInfo,
)

pytestmark = pytest.mark.unit

_MODEL_INFO = MLModelInfo(name="test-model", version="1.0.0", schema_version="1.0")


def _settings(**overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "app_env": "test",
        "ml_provider": "http",
        "ml_http_base_url": "http://ml.test",
        "ml_http_retries": 2,
        "ml_http_backoff_seconds": 0.001,
        "ml_http_timeout_seconds": 0.05,
    }
    values.update(overrides)
    return Settings(**values)


def _request(
    width: int = 1920, height: int = 1080, request_id: uuid.UUID | None = None
) -> MLInferenceRequest:
    return MLInferenceRequest(
        request_id=request_id if request_id is not None else uuid.uuid4(),
        image=MLImageRef(storage_key="tests/frame.jpg", width=width, height=height),
    )


def _response_payload(request: MLInferenceRequest) -> dict[str, Any]:
    response = MLInferenceResponse(
        request_id=request.request_id,
        model=_MODEL_INFO,
        detections=[
            MLDetection(
                object_type="telecom_well",
                condition_class="missing_cover",
                confidence=0.9,
                severity=5,
                bbox=MLBBox(x_min=10, y_min=10, x_max=200, y_max=200),
            )
        ],
        inference_time_ms=12.0,
    )
    return response.model_dump(mode="json")


def _http(
    handler: Callable[[httpx.Request], httpx.Response],
) -> tuple[HTTPMLProvider, httpx.AsyncClient]:
    settings = _settings()
    client = httpx.AsyncClient(
        base_url=settings.ml_http_base_url,
        transport=httpx.MockTransport(handler),
        timeout=settings.ml_http_timeout_seconds,
    )
    return HTTPMLProvider(settings, client=client), client


async def test_mock_implements_protocol() -> None:
    provider = MockMLProvider()
    assert isinstance(provider, MLProvider)
    assert provider.name == "mock"
    await provider.close()


async def test_mock_health_and_model_info() -> None:
    provider = MockMLProvider()
    health = await provider.health()
    assert health.status == "ok"
    assert health.model_loaded is True
    assert health.provider == "mock"
    assert health.details == {"note": "synthetic detections for demo/testing only"}
    info = await provider.model_info()
    assert info.name == "mock-infrastructure-detector"
    assert info.version == "0.1.0-mock"
    assert info.schema_version == "1.0"


async def test_mock_deterministic_per_request_id() -> None:
    request = _request(request_id=uuid.UUID("11111111-1111-4111-8111-111111111111"))
    first = await MockMLProvider().infer_image(request)
    second = await MockMLProvider().infer_image(request)
    assert first.detections == second.detections
    assert [d.detection_id for d in first.detections] == [d.detection_id for d in second.detections]
    assert first.model_dump(mode="json", exclude={"inference_time_ms"}) == second.model_dump(
        mode="json", exclude={"inference_time_ms"}
    )
    assert first.request_id == request.request_id


async def test_mock_bbox_within_image_for_100_random_sizes() -> None:
    provider = MockMLProvider()
    rng = random.Random(20260717)
    for i in range(100):
        width = rng.randint(320, 4096)
        height = rng.randint(240, 4096)
        request = _request(width, height, request_id=uuid.UUID(int=i, version=4))
        response = await provider.infer_image(request)
        for detection in response.detections:
            bbox = detection.bbox
            assert 0 <= bbox.x_min < bbox.x_max <= width
            assert 0 <= bbox.y_min < bbox.y_max <= height


async def test_mock_detection_fields_within_contract_ranges() -> None:
    provider = MockMLProvider()
    asset_codes = {t.code for t in all_asset_types()}
    for i in range(80):
        response = await provider.infer_image(
            _request(request_id=uuid.UUID(int=1000 + i, version=4))
        )
        assert 0 <= len(response.detections) <= 3
        for detection in response.detections:
            assert detection.object_type in asset_codes
            assert detection.condition_class in CANONICAL_CONDITIONS
            assert 0.55 <= detection.confidence <= 0.97
            assert detection.embedding is None
            assert detection.attributes == {"mock": True}
            if detection.condition_class in ("ok", "unknown"):
                assert detection.severity is None
            else:
                assert detection.severity == default_severity_for_condition(
                    detection.condition_class
                )
                assert 1 <= detection.severity <= 5


async def test_mock_produces_empty_results_and_unique_ids() -> None:
    provider = MockMLProvider()
    all_ids: list[uuid.UUID] = []
    empty_seen = False
    for i in range(60):
        response = await provider.infer_image(_request(request_id=uuid.UUID(int=i, version=4)))
        if not response.detections:
            empty_seen = True
        all_ids.extend(d.detection_id for d in response.detections)
    assert empty_seen, "expected at least one empty result among 60 deterministic requests"
    assert len(all_ids) == len(set(all_ids))


async def test_mock_batch_ok_consistency() -> None:
    provider = MockMLProvider()
    requests = [_request(request_id=uuid.UUID(int=i, version=4)) for i in range(3)]
    batch = await provider.infer_batch(requests)
    assert batch.schema_version == "1.0"
    assert batch.model.name == "mock-infrastructure-detector"
    assert [item.request_id for item in batch.results] == [r.request_id for r in requests]
    for item, request in zip(batch.results, requests, strict=True):
        assert item.status == "OK"
        assert item.error is None
        assert item.response is not None
        assert item.response.request_id == request.request_id


async def test_mock_batch_item_exception_becomes_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = MockMLProvider()
    requests = [_request(request_id=uuid.UUID(int=i, version=4)) for i in range(2)]
    failing_id = requests[1].request_id

    async def flaky(request: MLInferenceRequest) -> MLInferenceResponse:
        if request.request_id == failing_id:
            raise MLInferenceError("synthetic failure")
        return await MockMLProvider.infer_image(provider, request)

    monkeypatch.setattr(provider, "infer_image", flaky)
    batch = await provider.infer_batch(requests)
    assert batch.results[0].status == "OK"
    assert batch.results[1].status == "ERROR"
    assert batch.results[1].response is None
    assert batch.results[1].error is not None
    assert batch.results[1].error.code == "ml_inference_failed"
    assert batch.results[1].error.message == "synthetic failure"


async def test_factory_selects_provider_by_settings() -> None:
    mock = build_ml_provider(_settings(ml_provider="mock"))
    http = build_ml_provider(_settings(ml_provider="http"))
    try:
        assert isinstance(mock, MockMLProvider)
        assert isinstance(http, HTTPMLProvider)
        assert isinstance(mock, MLProvider)
        assert isinstance(http, MLProvider)
    finally:
        await mock.close()
        await http.close()


async def test_http_infer_success_roundtrip() -> None:
    request = _request()
    payload = _response_payload(request)
    seen: list[httpx.Request] = []

    def handler(http_request: httpx.Request) -> httpx.Response:
        seen.append(http_request)
        return httpx.Response(200, json=payload)

    provider, client = _http(handler)
    try:
        result = await provider.infer_image(request)
        assert result.model_dump(mode="json") == payload
        assert len(seen) == 1
        assert seen[0].method == "POST"
        assert seen[0].url.path == "/v1/infer"
        body = json.loads(seen[0].content)
        assert body["schema_version"] == "1.0"
        assert body["request_id"] == str(request.request_id)
        assert body["image"]["width"] == 1920
        assert body["image"]["height"] == 1080
    finally:
        await client.aclose()


async def test_http_invalid_json_raises_contract_error() -> None:
    def handler(http_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="{definitely-not-json")

    provider, client = _http(handler)
    try:
        with pytest.raises(MLContractError):
            await provider.infer_image(_request())
    finally:
        await client.aclose()


def _bad_confidence(payload: dict[str, Any]) -> None:
    payload["detections"][0]["confidence"] = 1.5


def _wrong_request_id(payload: dict[str, Any]) -> None:
    payload["request_id"] = str(uuid.UUID(int=999, version=4))


def _bbox_outside_image(payload: dict[str, Any]) -> None:
    payload["detections"][0]["bbox"]["x_max"] = 5000.0


def _wrong_schema_version(payload: dict[str, Any]) -> None:
    payload["schema_version"] = "2.0"


@pytest.mark.parametrize(
    "mutate",
    [_bad_confidence, _wrong_request_id, _bbox_outside_image, _wrong_schema_version],
    ids=["confidence-1.5", "request-id-mismatch", "bbox-outside", "schema-version-2.0"],
)
async def test_http_contract_violations_raise(
    mutate: Callable[[dict[str, Any]], None],
) -> None:
    request = _request()
    payload = _response_payload(request)
    mutate(payload)

    def handler(http_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    provider, client = _http(handler)
    try:
        with pytest.raises(MLContractError):
            await provider.infer_image(request)
    finally:
        await client.aclose()


async def test_http_timeout_retries_exactly_then_raises() -> None:
    calls = 0

    def handler(http_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise httpx.ReadTimeout("simulated timeout", request=http_request)

    provider, client = _http(handler)
    try:
        with pytest.raises(MLTimeoutError):
            await provider.infer_image(_request())
        assert calls == 3
    finally:
        await client.aclose()


async def test_http_retries_503_twice_then_succeeds() -> None:
    request = _request()
    payload = _response_payload(request)
    calls = 0

    def handler(http_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls <= 2:
            return httpx.Response(
                503, json={"error": {"code": "unavailable", "message": "warming up"}}
            )
        return httpx.Response(200, json=payload)

    provider, client = _http(handler)
    try:
        result = await provider.infer_image(request)
        assert result.request_id == request.request_id
        assert calls == 3
    finally:
        await client.aclose()


async def test_http_5xx_exhausted_raises_unavailable() -> None:
    calls = 0

    def handler(http_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(503, text="service unavailable")

    provider, client = _http(handler)
    try:
        with pytest.raises(MLUnavailableError):
            await provider.infer_image(_request())
        assert calls == 3
    finally:
        await client.aclose()


async def test_http_connect_error_retries_then_unavailable() -> None:
    calls = 0

    def handler(http_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise httpx.ConnectError("connection refused", request=http_request)

    provider, client = _http(handler)
    try:
        with pytest.raises(MLUnavailableError):
            await provider.infer_image(_request())
        assert calls == 3
    finally:
        await client.aclose()


async def test_http_400_no_retry_contract_error() -> None:
    calls = 0

    def handler(http_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(
            400, json={"error": {"code": "invalid_request", "message": "bad payload"}}
        )

    provider, client = _http(handler)
    try:
        with pytest.raises(MLContractError):
            await provider.infer_image(_request())
        assert calls == 1
    finally:
        await client.aclose()


async def test_http_inference_failed_body_raises_inference_error() -> None:
    calls = 0

    def handler(http_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(
            422,
            json={"error": {"code": "inference_failed", "message": "decode failed"}},
        )

    provider, client = _http(handler)
    try:
        with pytest.raises(MLInferenceError):
            await provider.infer_image(_request())
        assert calls == 1
    finally:
        await client.aclose()


async def test_http_error_metric_incremented() -> None:
    labels = {"provider": "http", "code": "ml_contract_violation"}
    before = REGISTRY.get_sample_value("ml_errors_total", labels) or 0.0

    def handler(http_request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": {"code": "invalid_request", "message": "x"}})

    provider, client = _http(handler)
    try:
        with pytest.raises(MLContractError):
            await provider.infer_image(_request())
        after = REGISTRY.get_sample_value("ml_errors_total", labels) or 0.0
        assert after == before + 1
    finally:
        await client.aclose()


async def test_http_batch_partial_errors_preserved() -> None:
    requests = [_request(request_id=uuid.UUID(int=i, version=4)) for i in range(2)]
    ok_response = MLInferenceResponse(
        request_id=requests[0].request_id, model=_MODEL_INFO, detections=[]
    )
    batch_payload = {
        "schema_version": "1.0",
        "model": _MODEL_INFO.model_dump(mode="json"),
        "results": [
            {
                "request_id": str(requests[0].request_id),
                "status": "OK",
                "response": ok_response.model_dump(mode="json"),
                "error": None,
            },
            {
                "request_id": str(requests[1].request_id),
                "status": "ERROR",
                "response": None,
                "error": {"code": "inference_failed", "message": "decode failed"},
            },
        ],
    }
    seen: list[httpx.Request] = []

    def handler(http_request: httpx.Request) -> httpx.Response:
        seen.append(http_request)
        return httpx.Response(200, json=batch_payload)

    provider, client = _http(handler)
    try:
        batch = await provider.infer_batch(requests)
        assert batch.results[0].status == "OK"
        assert batch.results[0].response is not None
        assert batch.results[0].response.request_id == requests[0].request_id
        assert batch.results[1].status == "ERROR"
        assert batch.results[1].response is None
        assert batch.results[1].error is not None
        assert batch.results[1].error.code == "inference_failed"
        assert seen[0].url.path == "/v1/infer/batch"
        body = json.loads(seen[0].content)
        assert body["schema_version"] == "1.0"
        assert [item["request_id"] for item in body["requests"]] == [
            str(r.request_id) for r in requests
        ]
    finally:
        await client.aclose()


async def test_http_batch_unknown_request_id_raises() -> None:
    requests = [_request(request_id=uuid.UUID(int=0, version=4))]
    foreign_id = uuid.UUID(int=777, version=4)
    ok_response = MLInferenceResponse(request_id=foreign_id, model=_MODEL_INFO, detections=[])
    batch_payload = {
        "schema_version": "1.0",
        "model": _MODEL_INFO.model_dump(mode="json"),
        "results": [
            {
                "request_id": str(foreign_id),
                "status": "OK",
                "response": ok_response.model_dump(mode="json"),
                "error": None,
            }
        ],
    }

    def handler(http_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=batch_payload)

    provider, client = _http(handler)
    try:
        with pytest.raises(MLContractError):
            await provider.infer_batch(requests)
    finally:
        await client.aclose()


async def test_http_batch_transport_failure_raises() -> None:
    def handler(http_request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="down")

    provider, client = _http(handler)
    try:
        with pytest.raises(MLUnavailableError):
            await provider.infer_batch([_request()])
    finally:
        await client.aclose()


async def test_http_health_and_model_info() -> None:
    def handler(http_request: httpx.Request) -> httpx.Response:
        if http_request.url.path == "/v1/health":
            return httpx.Response(
                200,
                json={"status": "ok", "model_loaded": True, "provider": "http", "details": {}},
            )
        assert http_request.url.path == "/v1/model-info"
        return httpx.Response(200, json=_MODEL_INFO.model_dump(mode="json"))

    provider, client = _http(handler)
    try:
        health = await provider.health()
        assert health.status == "ok"
        assert health.model_loaded is True
        info = await provider.model_info()
        assert info == _MODEL_INFO
    finally:
        await client.aclose()


async def test_http_close_only_closes_owned_client() -> None:
    provider, client = _http(lambda http_request: httpx.Response(200))
    await provider.close()
    assert not client.is_closed
    await client.aclose()

    owned = HTTPMLProvider(_settings())
    await owned.close()
    assert owned._client.is_closed
