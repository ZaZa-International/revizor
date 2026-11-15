"""Frontend contract: error envelope, pagination, GeoJSON order, end-to-end workflows."""

from __future__ import annotations

import json
import uuid

import pytest

from tests.api.test_assets_api import (
    seed_asset,
    seed_observation_chain,
    seed_upload_with_file,
)
from tests.fixtures.media import make_jpeg_bytes, upload_metadata

pytestmark = pytest.mark.contract


@pytest.fixture(autouse=True)
def _fast_error_logging(app, settings):
    from app.core.logging import configure_logging

    configure_logging(settings.log_level, "json")


def _assert_error_envelope(response, status: int) -> dict:
    assert response.status_code == status, response.text
    body = response.json()
    assert set(body) == {"error"}
    error = body["error"]
    assert set(error) == {"code", "message", "details", "request_id"}
    assert isinstance(error["code"], str) and error["code"]
    assert isinstance(error["message"], str) and error["message"]
    assert isinstance(error["details"], list)
    assert isinstance(error["request_id"], str) and error["request_id"]
    return error


def _assert_page_envelope(body: dict) -> None:
    assert set(body) == {"items", "total", "page", "page_size", "pages"}
    assert isinstance(body["items"], list)
    for field in ("total", "page", "page_size", "pages"):
        assert isinstance(body[field], int), field
        assert body[field] >= 0
    assert body["page"] >= 1
    assert body["page_size"] >= 1


async def test_error_envelope_on_404(client, admin_headers):
    response = await client.get(f"/api/v1/assets/{uuid.uuid4()}", headers=admin_headers)
    error = _assert_error_envelope(response, 404)
    assert error["code"] == "not_found"


async def test_error_envelope_on_422(client, admin_headers):
    response = await client.get("/api/v1/assets", headers=admin_headers, params={"bbox": "garbage"})
    error = _assert_error_envelope(response, 422)
    assert error["code"] == "validation_error"


async def test_error_envelope_on_401(client):
    response = await client.get("/api/v1/auth/me")
    error = _assert_error_envelope(response, 401)
    assert error["code"] == "authentication_failed"


async def test_pagination_envelope_fields_and_types(client, admin_headers):
    response = await client.get("/api/v1/uploads", headers=admin_headers)
    assert response.status_code == 200
    _assert_page_envelope(response.json())


async def test_geojson_feature_collection_coordinate_order(client, admin_headers, database):
    await seed_asset(database, lon=37.6173, lat=55.7558)
    response = await client.get("/api/v1/map/assets", headers=admin_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["type"] == "FeatureCollection"
    assert len(body["features"]) == 1
    geometry = body["features"][0]["geometry"]
    assert geometry["type"] == "Point"
    assert len(geometry["coordinates"]) == 2
    lon, lat = geometry["coordinates"]
    assert lon == pytest.approx(37.6173)
    assert lat == pytest.approx(55.7558)


async def test_upload_job_observations_workflow(client, admin_headers):
    upload = await client.post(
        "/api/v1/uploads",
        headers=admin_headers,
        files={"file": ("workflow.jpg", make_jpeg_bytes(seed=51), "image/jpeg")},
        data={"metadata": json.dumps(upload_metadata())},
    )
    assert upload.status_code == 201, upload.text
    upload_id = upload.json()["upload"]["id"]
    await _assert_job_observations_workflow(client, admin_headers, upload_id)


async def test_upload_job_observations_workflow_seeded_upload(
    client, admin_headers, database, settings
):
    upload_id = await seed_upload_with_file(
        database, settings.storage_local_path, metadata=upload_metadata(), seed=51
    )
    await _assert_job_observations_workflow(client, admin_headers, upload_id)


async def _assert_job_observations_workflow(client, headers, upload_id):
    job = await client.post("/api/v1/jobs", headers=headers, json={"upload_id": str(upload_id)})
    assert job.status_code == 201, job.text
    job_id = job.json()["id"]

    observations = await client.get(
        "/api/v1/observations", headers=headers, params={"job_id": job_id}
    )
    assert observations.status_code == 200
    body = observations.json()
    _assert_page_envelope(body)
    for item in body["items"]:
        assert item["processing_job_id"] == job_id
        assert "review_status" in item
        assert "effective_condition" in item


async def test_review_workflow_shape(client, admin_headers, database):
    chain = await seed_observation_chain(database)
    created = await client.post(
        "/api/v1/reviews",
        headers=admin_headers,
        json={"observation_id": str(chain.observation_id), "decision": "CONFIRMED"},
    )
    await _assert_review_workflow_shape(client, admin_headers, chain, created)


async def test_review_workflow_shape_explicit_reviewed_at(client, admin_headers, database):
    chain = await seed_observation_chain(database)
    created = await client.post(
        "/api/v1/reviews",
        headers=admin_headers,
        json={
            "observation_id": str(chain.observation_id),
            "decision": "CONFIRMED",
            "reviewed_at": "2026-11-15T12:00:00",
        },
    )
    await _assert_review_workflow_shape(client, admin_headers, chain, created)


async def _assert_review_workflow_shape(client, headers, chain, created):
    assert created.status_code == 201, created.text
    review = created.json()
    assert set(review) == {
        "id",
        "observation_id",
        "defect_id",
        "reviewer_id",
        "decision",
        "corrected_asset_type",
        "corrected_condition",
        "corrected_defect_type",
        "corrected_severity",
        "comment",
        "reviewed_at",
        "created_at",
    }
    assert review["decision"] == "CONFIRMED"

    listing = await client.get(
        "/api/v1/reviews",
        headers=headers,
        params={"observation_id": str(chain.observation_id)},
    )
    assert listing.status_code == 200
    _assert_page_envelope(listing.json())
    assert listing.json()["total"] == 1

    observation = await client.get(f"/api/v1/observations/{chain.observation_id}", headers=headers)
    assert observation.status_code == 200
    assert observation.json()["review_status"] == "CONFIRMED"


async def test_export_content_disposition_header(client, admin_headers, database):
    await seed_asset(database)
    response = await client.get("/api/v1/exports/assets", headers=admin_headers)
    assert response.status_code == 200
    disposition = response.headers["content-disposition"]
    assert disposition.startswith("attachment")
    assert "filename=" in disposition
    assert "assets-export-" in disposition
