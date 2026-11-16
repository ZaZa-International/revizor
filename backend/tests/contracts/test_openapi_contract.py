"""OpenAPI contract tests for the developer portal tooling.

No external services are required: the app is built in-memory via create_app()
and its lifespan is NEVER started (no DB/Redis/S3 connections). The autouse
DB-cleaning fixture from tests/conftest.py is overridden below.

ML contract consistency (JSON schemas <-> examples <-> Pydantic models) is
covered by tests/contracts/test_ml_contract.py and is not duplicated here.
"""

from __future__ import annotations

import difflib
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from app.schemas.common import ErrorResponse
from fastapi import FastAPI
from fastapi.routing import APIRoute, RouteContext, iter_route_contexts
from jsonschema import Draft202012Validator  # type: ignore[import-untyped]
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

pytestmark = pytest.mark.contract

_REPO_ROOT = Path(__file__).resolve().parents[3]
_COMMITTED_OPENAPI = _REPO_ROOT / "contracts" / "openapi" / "openapi.json"
_EXAMPLES_DIR = _REPO_ROOT / "contracts" / "examples" / "api"
_OPENAPI_BASE_URI = "urn:mgts:openapi"

KNOWN_TAGS = {
    "System & Health",
    "Authentication & Users",
    "Uploads & Media",
    "Processing Jobs",
    "Infrastructure Assets",
    "Observations",
    "Defects & Risk",
    "Reviews & Human-in-the-loop",
    "Geospatial & Maps",
    "Routes & Inspections",
    "Analytics & Coverage",
    "Exports & Reports",
    "ML Integration",
    "Storage & Files",
}

BINARY_OPERATION_PREFIXES = ("/api/v1/exports/", "/api/v1/files/")

EXAMPLE_COMPONENTS = {
    "login-response.json": "TokenResponse",
    "upload-created.json": "UploadCreateResponse",
    "upload-duplicate-redacted.json": "UploadCreateResponse",
    "job-completed.json": "JobResponse",
    "job-frames-page.json": "PageResponse_JobFrameResponse_",
    "assets-page.json": "PageResponse_AssetResponse_",
    "asset-detail.json": "AssetResponse",
    "observation-detail.json": "ObservationResponse",
    "defects-page.json": "PageResponse_DefectResponse_",
    "review-created.json": "ReviewResponse",
    "map-assets-featurecollection.json": "FeatureCollection_AssetMapProperties_",
    "routes-page.json": "PageResponse_RouteResponse_",
    "analytics-overview.json": "AnalyticsOverview",
    "analytics-coverage.json": "CoverageResponse",
    "error-not-found.json": "ErrorResponse",
    "error-validation.json": "ErrorResponse",
    "error-conflict.json": "ErrorResponse",
    "error-rate-limited.json": "ErrorResponse",
}


@pytest.fixture(autouse=True)
def clean_tables() -> Iterator[None]:
    """Override the conftest autouse fixture: these tests never touch the DB."""
    yield


@pytest.fixture(scope="module")
def app() -> FastAPI:
    from app.main import create_app

    return create_app()


@pytest.fixture(scope="module")
def live_openapi(app: FastAPI) -> dict[str, Any]:
    return app.openapi()


@pytest.fixture(scope="module")
def committed_openapi() -> dict[str, Any]:
    return json.loads(_COMMITTED_OPENAPI.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def registry(live_openapi: dict[str, Any]) -> Registry:
    return Registry().with_resource(
        _OPENAPI_BASE_URI,
        Resource.from_contents(live_openapi, default_specification=DRAFT202012),
    )


def _api_route_contexts(app: FastAPI) -> Iterator[RouteContext]:
    """Resolved API routes, using the same traversal as FastAPI's openapi().

    FastAPI >= 0.163 keeps included routers lazy (_IncludedRouter), so a plain
    isinstance scan of app.routes would miss every nested endpoint.
    """
    for context in iter_route_contexts(app.routes):
        if isinstance(context.original_route, APIRoute) and context.include_in_schema:
            yield context


def _operations(app: FastAPI, schema: dict[str, Any]) -> list[tuple[str, str, dict[str, Any]]]:
    operations: list[tuple[str, str, dict[str, Any]]] = []
    for context in _api_route_contexts(app):
        path = context.path_format or ""
        for method in sorted(context.methods or set()):
            operation = schema["paths"][path][method.lower()]
            operations.append((method, path, operation))
    return operations


def _is_binary_operation(path: str) -> bool:
    return path.startswith(BINARY_OPERATION_PREFIXES)


def _component_validator(
    component: str, live_openapi: dict[str, Any], registry: Registry
) -> Draft202012Validator:
    components = live_openapi.get("components", {}).get("schemas", {})
    if component in components:
        schema: dict[str, Any] = {"$ref": f"{_OPENAPI_BASE_URI}#/components/schemas/{component}"}
    elif component == "ErrorResponse":
        schema = ErrorResponse.model_json_schema()
    else:
        pytest.fail(f"Component schema '{component}' is missing from the live OpenAPI document")
    return Draft202012Validator(
        schema, registry=registry, format_checker=Draft202012Validator.FORMAT_CHECKER
    )


def test_every_operation_has_summary(app: FastAPI, live_openapi: dict[str, Any]) -> None:
    missing = [
        f"{method} {path}"
        for method, path, operation in _operations(app, live_openapi)
        if not (operation.get("summary") or "").strip()
    ]
    assert not missing, f"operations without summary: {missing}"


def test_every_operation_has_description(app: FastAPI, live_openapi: dict[str, Any]) -> None:
    missing = [
        f"{method} {path}"
        for method, path, operation in _operations(app, live_openapi)
        if not (operation.get("description") or "").strip()
    ]
    assert not missing, f"operations without description: {missing}"


def test_json_operations_have_2xx_schema(app: FastAPI, live_openapi: dict[str, Any]) -> None:
    problems: list[str] = []
    for method, path, operation in _operations(app, live_openapi):
        if _is_binary_operation(path):
            continue
        for code, response in operation.get("responses", {}).items():
            if not code.startswith("2") or code == "204":
                continue
            content = response.get("content", {})
            if not content:
                problems.append(f"{method} {path} {code}: no content")
                continue
            for media_type, body in content.items():
                if not body.get("schema"):
                    problems.append(f"{method} {path} {code} {media_type}: empty schema")
    assert not problems, "2xx responses without schema:\n" + "\n".join(problems)


def test_export_and_file_operations_declare_binary_schema(
    app: FastAPI, live_openapi: dict[str, Any]
) -> None:
    problems: list[str] = []
    checked = 0
    for method, path, operation in _operations(app, live_openapi):
        if not _is_binary_operation(path):
            continue
        for code, response in operation.get("responses", {}).items():
            if not code.startswith("2"):
                continue
            checked += 1
            content = response.get("content", {})
            if not content:
                problems.append(f"{method} {path} {code}: no content")
                continue
            for media_type, body in content.items():
                schema = body.get("schema") or {}
                if media_type == "application/json" or schema.get("type") != "string":
                    problems.append(
                        f"{method} {path} {code} {media_type}: expected binary string schema"
                    )
    assert checked > 0, "no export/file operations found"
    assert not problems, "binary responses misdeclared:\n" + "\n".join(problems)


def test_operation_ids_unique_and_stable(app: FastAPI, live_openapi: dict[str, Any]) -> None:
    """operationId must equal the endpoint function name and be globally unique."""
    seen: dict[str, str] = {}
    problems: list[str] = []
    count = 0
    for context in _api_route_contexts(app):
        path = context.path_format or ""
        for method in sorted(context.methods or set()):
            count += 1
            operation = live_openapi["paths"][path][method.lower()]
            operation_id = operation.get("operationId", "")
            expected = context.name or ""
            if operation_id != expected:
                problems.append(f"{method} {path}: operationId '{operation_id}' != '{expected}'")
            if operation_id in seen:
                problems.append(
                    f"duplicate operationId '{operation_id}': {seen[operation_id]} / {path}"
                )
            seen[operation_id] = f"{method} {path}"
    assert count > 0, "no API operations resolved from the app"
    assert not problems, "operationId contract violations:\n" + "\n".join(problems)


def test_tags_within_known_sections(app: FastAPI, live_openapi: dict[str, Any]) -> None:
    problems: list[str] = []
    used: set[str] = set()
    for method, path, operation in _operations(app, live_openapi):
        tags = operation.get("tags") or []
        if not tags:
            problems.append(f"{method} {path}: no tags")
        for tag in tags:
            used.add(tag)
            if tag not in KNOWN_TAGS:
                problems.append(f"{method} {path}: unknown tag '{tag}'")
    assert not problems, "tag contract violations:\n" + "\n".join(problems)
    assert used == KNOWN_TAGS, f"expected all 14 sections to be used, got {sorted(used)}"


def test_error_response_component_declared(live_openapi: dict[str, Any]) -> None:
    components = live_openapi.get("components", {}).get("schemas", {})
    assert "ErrorResponse" in components, "ErrorResponse must be a declared component schema"
    schema = components["ErrorResponse"]
    assert "error" in schema.get("properties", {}), "ErrorResponse must expose the error envelope"


def test_declared_422_references_error_response(app: FastAPI, live_openapi: dict[str, Any]) -> None:
    problems: list[str] = []
    for method, path, operation in _operations(app, live_openapi):
        response = operation.get("responses", {}).get("422")
        if response is None:
            continue
        for media_type, body in response.get("content", {}).items():
            ref = (body.get("schema") or {}).get("$ref", "")
            if not ref.endswith("/ErrorResponse"):
                problems.append(f"{method} {path} 422 {media_type}: {ref or 'no $ref'}")
    assert not problems, "422 must reference ErrorResponse:\n" + "\n".join(problems)


def test_error_envelope_examples_match_error_response_model() -> None:
    validator = Draft202012Validator(
        ErrorResponse.model_json_schema(), format_checker=Draft202012Validator.FORMAT_CHECKER
    )
    error_examples = sorted(_EXAMPLES_DIR.glob("error-*.json"))
    assert error_examples, "error envelope examples are missing"
    for example_path in error_examples:
        envelope = json.loads(example_path.read_text(encoding="utf-8"))
        errors = list(validator.iter_errors(envelope))
        assert not errors, f"{example_path.name}: {[e.message for e in errors]}"


def test_committed_openapi_matches_live(
    committed_openapi: dict[str, Any], live_openapi: dict[str, Any]
) -> None:
    committed_text = json.dumps(committed_openapi, indent=2, ensure_ascii=False, sort_keys=True)
    live_text = json.dumps(live_openapi, indent=2, ensure_ascii=False, sort_keys=True)
    if committed_text == live_text:
        return
    diff = list(
        difflib.unified_diff(
            committed_text.splitlines(),
            live_text.splitlines(),
            fromfile="contracts/openapi/openapi.json",
            tofile="live app.openapi()",
            lineterm="",
            n=1,
        )
    )
    summary = "\n".join(diff[:60])
    pytest.fail(
        f"committed OpenAPI drifted from the live app ({len(diff)} diff lines); "
        f"run `make openapi`.\n{summary}"
    )


@pytest.mark.parametrize("example_name", sorted(EXAMPLE_COMPONENTS))
def test_api_examples_validate_against_component_schemas(
    example_name: str, live_openapi: dict[str, Any], registry: Registry
) -> None:
    example_path = _EXAMPLES_DIR / example_name
    assert example_path.exists(), f"missing example file: {example_path}"
    example = json.loads(example_path.read_text(encoding="utf-8"))
    validator = _component_validator(EXAMPLE_COMPONENTS[example_name], live_openapi, registry)
    errors = list(validator.iter_errors(example))
    assert not errors, f"{example_name} violates {EXAMPLE_COMPONENTS[example_name]}: " + "; ".join(
        f"{list(e.absolute_path)}: {e.message}" for e in errors[:5]
    )


def test_example_files_all_covered_by_contract() -> None:
    on_disk = {path.name for path in _EXAMPLES_DIR.glob("*.json")}
    assert on_disk == set(EXAMPLE_COMPONENTS), (
        f"uncovered examples: {sorted(on_disk - set(EXAMPLE_COMPONENTS))}; "
        f"missing examples: {sorted(set(EXAMPLE_COMPONENTS) - on_disk)}"
    )
