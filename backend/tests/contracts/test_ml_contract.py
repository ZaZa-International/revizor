"""Contract tests: JSON schemas, example payloads and Pydantic models must agree.

JSON Schema draft 2020-12 cannot express cross-field ordering (bbox min < max)
or uniqueness of a key across array items (detection_id). Those rules are
enforced by the Pydantic models in app/schemas/ml.py and are tested here via
model validation; the schemas cover everything expressible in the standard.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest
from app.schemas.ml import (
    MLBatchResponse,
    MLBBox,
    MLDetection,
    MLHealth,
    MLInferenceRequest,
    MLInferenceResponse,
    MLModelInfo,
)
from jsonschema import Draft202012Validator
from pydantic import BaseModel, ValidationError
from referencing import Registry, Resource

pytestmark = pytest.mark.contract

_REPO_ROOT = Path(__file__).resolve().parents[3]
_CONTRACTS_DIR = _REPO_ROOT / "contracts" / "ml"
_EXAMPLES_DIR = _CONTRACTS_DIR / "examples"

_SCHEMA_FILES = {
    "inference-request": "inference-request.schema.json",
    "inference-response": "inference-response.schema.json",
    "batch-request": "batch-request.schema.json",
    "batch-response": "batch-response.schema.json",
    "error-response": "error-response.schema.json",
    "health": "health.schema.json",
    "model-info": "model-info.schema.json",
}

_EXAMPLE_SCHEMA_PAIRS = [
    ("request.json", "inference-request"),
    ("response.json", "inference-response"),
    ("response-empty.json", "inference-response"),
    ("batch-request.json", "batch-request"),
    ("batch-response-partial.json", "batch-response"),
    ("error.json", "error-response"),
]


def _load_schema(name: str) -> dict[str, Any]:
    return json.loads((_CONTRACTS_DIR / _SCHEMA_FILES[name]).read_text(encoding="utf-8"))


def _load_example(filename: str) -> dict[str, Any]:
    return json.loads((_EXAMPLES_DIR / filename).read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def schemas() -> dict[str, dict[str, Any]]:
    return {name: _load_schema(name) for name in _SCHEMA_FILES}


@pytest.fixture(scope="module")
def registry(schemas: dict[str, dict[str, Any]]) -> Registry:
    return Registry().with_resources(
        [(schema["$id"], Resource.from_contents(schema)) for schema in schemas.values()]
    )


def _validator(schema: dict[str, Any], registry: Registry) -> Draft202012Validator:
    return Draft202012Validator(
        schema, registry=registry, format_checker=Draft202012Validator.FORMAT_CHECKER
    )


def _assert_valid(
    payload: dict[str, Any],
    schema_name: str,
    schemas: dict[str, dict[str, Any]],
    registry: Registry,
) -> None:
    errors = list(_validator(schemas[schema_name], registry).iter_errors(payload))
    assert errors == [], f"{schema_name}: {[e.message for e in errors]}"


def _assert_schema_rejects(
    payload: dict[str, Any],
    schema_name: str,
    schemas: dict[str, dict[str, Any]],
    registry: Registry,
) -> None:
    errors = list(_validator(schemas[schema_name], registry).iter_errors(payload))
    assert errors, f"{schema_name} unexpectedly accepted invalid payload"


def test_all_schemas_are_valid_draft202012(schemas: dict[str, dict[str, Any]]) -> None:
    for name, schema in schemas.items():
        Draft202012Validator.check_schema(schema)
        assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema", name


@pytest.mark.parametrize(("example", "schema_name"), _EXAMPLE_SCHEMA_PAIRS)
def test_examples_validate_against_schemas(
    example: str,
    schema_name: str,
    schemas: dict[str, dict[str, Any]],
    registry: Registry,
) -> None:
    _assert_valid(_load_example(example), schema_name, schemas, registry)


@pytest.mark.parametrize(
    ("example", "schema_name", "model"),
    [
        ("request.json", "inference-request", MLInferenceRequest),
        ("response.json", "inference-response", MLInferenceResponse),
        ("response-empty.json", "inference-response", MLInferenceResponse),
        ("batch-response-partial.json", "batch-response", MLBatchResponse),
    ],
)
def test_pydantic_roundtrip_through_schemas(
    example: str,
    schema_name: str,
    model: type[BaseModel],
    schemas: dict[str, dict[str, Any]],
    registry: Registry,
) -> None:
    parsed = model.model_validate(_load_example(example))
    _assert_valid(parsed.model_dump(mode="json"), schema_name, schemas, registry)


def test_batch_request_body_roundtrip(
    schemas: dict[str, dict[str, Any]], registry: Registry
) -> None:
    request = MLInferenceRequest.model_validate(_load_example("request.json"))
    body = {"schema_version": "1.0", "requests": [request.model_dump(mode="json")]}
    _assert_valid(body, "batch-request", schemas, registry)
    example_body = _load_example("batch-request.json")
    parsed = [MLInferenceRequest.model_validate(item) for item in example_body["requests"]]
    rebuilt = {
        "schema_version": "1.0",
        "requests": [item.model_dump(mode="json") for item in parsed],
    }
    _assert_valid(rebuilt, "batch-request", schemas, registry)


def test_health_and_model_info_roundtrip(
    schemas: dict[str, dict[str, Any]], registry: Registry
) -> None:
    health = MLHealth(status="ok", model_loaded=True, provider="http", details={"gpu": "available"})
    _assert_valid(health.model_dump(mode="json"), "health", schemas, registry)
    info = MLModelInfo(name="infrastructure-detector", version="1.2.0", schema_version="1.0")
    _assert_valid(info.model_dump(mode="json"), "model-info", schemas, registry)


def test_error_example_matches_error_envelope(
    schemas: dict[str, dict[str, Any]], registry: Registry
) -> None:
    payload = _load_example("error.json")
    _assert_valid(payload, "error-response", schemas, registry)
    assert set(payload) == {"error"}
    error = payload["error"]
    assert {"code", "message"} <= set(error)
    assert error["code"] == "inference_failed"
    assert isinstance(error["message"], str) and error["message"]


def test_schema_rejects_confidence_above_one(
    schemas: dict[str, dict[str, Any]], registry: Registry
) -> None:
    payload = _load_example("response.json")
    payload["detections"][0]["confidence"] = 1.5
    _assert_schema_rejects(payload, "inference-response", schemas, registry)
    with pytest.raises(ValidationError):
        MLInferenceResponse.model_validate(payload)


def test_schema_rejects_missing_request_id(
    schemas: dict[str, dict[str, Any]], registry: Registry
) -> None:
    payload = _load_example("request.json")
    del payload["request_id"]
    _assert_schema_rejects(payload, "inference-request", schemas, registry)


def test_schema_rejects_wrong_schema_version(
    schemas: dict[str, dict[str, Any]], registry: Registry
) -> None:
    for example, schema_name in [
        ("request.json", "inference-request"),
        ("response.json", "inference-response"),
        ("batch-request.json", "batch-request"),
        ("batch-response-partial.json", "batch-response"),
    ]:
        payload = _load_example(example)
        payload["schema_version"] = "2.0"
        _assert_schema_rejects(payload, schema_name, schemas, registry)


def test_schema_rejects_batch_ok_without_response(
    schemas: dict[str, dict[str, Any]], registry: Registry
) -> None:
    payload = _load_example("batch-response-partial.json")
    ok_item = payload["results"][0]
    assert ok_item["status"] == "OK"
    del ok_item["response"]
    _assert_schema_rejects(payload, "batch-response", schemas, registry)
    with pytest.raises(ValidationError):
        MLBatchResponse.model_validate(payload)


def test_schema_rejects_batch_error_without_error(
    schemas: dict[str, dict[str, Any]], registry: Registry
) -> None:
    payload = _load_example("batch-response-partial.json")
    error_item = payload["results"][1]
    assert error_item["status"] == "ERROR"
    del error_item["error"]
    _assert_schema_rejects(payload, "batch-response", schemas, registry)
    with pytest.raises(ValidationError):
        MLBatchResponse.model_validate(payload)


def test_inverted_bbox_rejected_by_pydantic() -> None:
    with pytest.raises(ValidationError):
        MLBBox(x_min=100, y_min=10, x_max=50, y_max=200)
    with pytest.raises(ValidationError):
        MLBBox(x_min=10, y_min=100, x_max=200, y_max=50)
    payload = _load_example("response.json")
    payload["detections"][0]["bbox"] = {"x_min": 100, "y_min": 10, "x_max": 50, "y_max": 200}
    with pytest.raises(ValidationError):
        MLInferenceResponse.model_validate(payload)


def test_duplicate_detection_id_rejected() -> None:
    payload = _load_example("response.json")
    duplicate = copy.deepcopy(payload["detections"][0])
    duplicate["bbox"] = {"x_min": 1, "y_min": 1, "x_max": 2, "y_max": 2}
    payload["detections"].append(duplicate)
    with pytest.raises(ValidationError):
        MLInferenceResponse.model_validate(payload)


def test_identical_duplicate_detections_rejected_by_schema(
    schemas: dict[str, dict[str, Any]], registry: Registry
) -> None:
    payload = _load_example("response.json")
    payload["detections"].append(copy.deepcopy(payload["detections"][0]))
    _assert_schema_rejects(payload, "inference-response", schemas, registry)


def test_schema_rejects_unpaired_geo_coordinates(
    schemas: dict[str, dict[str, Any]], registry: Registry
) -> None:
    payload = _load_example("request.json")
    del payload["metadata"]["latitude"]
    _assert_schema_rejects(payload, "inference-request", schemas, registry)
    with pytest.raises(ValidationError):
        MLInferenceRequest.model_validate(payload)


def test_schema_rejects_extra_fields(
    schemas: dict[str, dict[str, Any]], registry: Registry
) -> None:
    payload = _load_example("request.json")
    payload["unexpected_field"] = True
    _assert_schema_rejects(payload, "inference-request", schemas, registry)
    with pytest.raises(ValidationError):
        MLInferenceRequest.model_validate(payload)


def test_schema_rejects_invalid_detection_fields(
    schemas: dict[str, dict[str, Any]], registry: Registry
) -> None:
    payload = _load_example("response.json")
    payload["detections"][0]["severity"] = 6
    _assert_schema_rejects(payload, "inference-response", schemas, registry)
    payload = _load_example("response.json")
    payload["detections"][0]["bbox"]["x_min"] = -1
    _assert_schema_rejects(payload, "inference-response", schemas, registry)
    payload = _load_example("request.json")
    payload["image"]["width"] = 0
    _assert_schema_rejects(payload, "inference-request", schemas, registry)


def test_detection_model_roundtrip_minimal(
    schemas: dict[str, dict[str, Any]], registry: Registry
) -> None:
    detection = MLDetection(
        object_type="pole",
        confidence=0.7,
        bbox=MLBBox(x_min=0, y_min=0, x_max=10, y_max=10),
    )
    response = MLInferenceResponse(
        request_id=MLInferenceRequest.model_validate(_load_example("request.json")).request_id,
        model=MLModelInfo(name="m", version="0", schema_version="1.0"),
        detections=[detection],
    )
    _assert_valid(response.model_dump(mode="json"), "inference-response", schemas, registry)
