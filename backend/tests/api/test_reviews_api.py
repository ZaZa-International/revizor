"""Reviews API: append-only decisions, effective state, defects, training examples."""

from __future__ import annotations

import uuid

import pytest
from app.infrastructure.database.models.training import TrainingExample
from app.infrastructure.database.models.user import User
from sqlalchemy import select

from tests.api.test_assets_api import seed_observation_chain

pytestmark = pytest.mark.api

_REVIEW_TZ_BUG = (
    "BUG: Review.reviewed_at is a timezone-naive ORM column "
    "(app/infrastructure/database/models/review.py:44) while the migration creates "
    "TIMESTAMPTZ; ReviewService defaults reviewed_at to aware datetime.now(UTC) "
    "(app/application/services/reviews.py:110) and asyncpg rejects the bind at the "
    "flush (reviews.py:113), so POST /reviews without reviewed_at fails with 500"
)
_NAIVE_REVIEWED_AT = "2026-11-15T12:00:00"


@pytest.fixture(autouse=True)
def _fast_error_logging(app, settings):
    from app.core.logging import configure_logging

    configure_logging(settings.log_level, "json")


async def _admin_id(database) -> uuid.UUID:
    async with database.session() as session:
        return (await session.execute(select(User.id).where(User.username == "admin"))).scalar_one()


async def _get_observation(client, headers, observation_id) -> dict:
    response = await client.get(f"/api/v1/observations/{observation_id}", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


async def _training_example(database, observation_id) -> TrainingExample | None:
    async with database.session() as session:
        return (
            await session.execute(
                select(TrainingExample).where(TrainingExample.observation_id == observation_id)
            )
        ).scalar_one_or_none()


async def test_confirm_review_updates_observation(client, admin_headers, database):
    chain = await seed_observation_chain(database)
    response = await client.post(
        "/api/v1/reviews",
        headers=admin_headers,
        json={
            "observation_id": str(chain.observation_id),
            "decision": "CONFIRMED",
            "comment": "looks right",
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["decision"] == "CONFIRMED"
    assert body["observation_id"] == str(chain.observation_id)
    assert body["reviewer_id"] == str(await _admin_id(database))

    observation = await _get_observation(client, admin_headers, chain.observation_id)
    assert observation["review_status"] == "CONFIRMED"
    assert observation["effective_asset_type"] == "telecom_well"
    assert observation["effective_condition"] == "damaged_cover"
    assert observation["effective_severity"] == 4
    assert observation["condition_class"] == "damaged_cover"
    assert observation["severity"] == 4


async def test_corrected_review_updates_observation_and_asset(client, admin_headers, database):
    chain = await seed_observation_chain(database)
    response = await client.post(
        "/api/v1/reviews",
        headers=admin_headers,
        json={
            "observation_id": str(chain.observation_id),
            "decision": "CORRECTED",
            "corrected_severity": 2,
            "corrected_condition": "ok",
        },
    )
    assert response.status_code == 201, response.text
    observation = await _get_observation(client, admin_headers, chain.observation_id)
    assert observation["review_status"] == "CORRECTED"
    assert observation["effective_severity"] == 2
    assert observation["effective_condition"] == "ok"
    assert observation["severity"] == 4

    asset = await client.get(f"/api/v1/assets/{chain.asset_id}", headers=admin_headers)
    assert asset.status_code == 200
    assert asset.json()["current_severity"] == 2
    assert asset.json()["current_condition"] == "ok"


async def test_rejected_review(client, admin_headers, database):
    chain = await seed_observation_chain(database)
    response = await client.post(
        "/api/v1/reviews",
        headers=admin_headers,
        json={"observation_id": str(chain.observation_id), "decision": "REJECTED"},
    )
    assert response.status_code == 201, response.text
    observation = await _get_observation(client, admin_headers, chain.observation_id)
    assert observation["review_status"] == "REJECTED"


async def test_reviews_are_append_only(client, admin_headers, database):
    chain = await seed_observation_chain(database)
    first = await client.post(
        "/api/v1/reviews",
        headers=admin_headers,
        json={"observation_id": str(chain.observation_id), "decision": "CONFIRMED"},
    )
    assert first.status_code == 201
    second = await client.post(
        "/api/v1/reviews",
        headers=admin_headers,
        json={"observation_id": str(chain.observation_id), "decision": "REJECTED"},
    )
    assert second.status_code == 201, second.text
    assert second.json()["id"] != first.json()["id"]

    listing = await client.get(
        "/api/v1/reviews",
        headers=admin_headers,
        params={"observation_id": str(chain.observation_id)},
    )
    assert listing.status_code == 200
    assert listing.json()["total"] >= 2


async def test_corrected_without_correction_422(client, admin_headers, database):
    chain = await seed_observation_chain(database)
    response = await client.post(
        "/api/v1/reviews",
        headers=admin_headers,
        json={"observation_id": str(chain.observation_id), "decision": "CORRECTED"},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


async def test_review_without_target_422(client, admin_headers):
    response = await client.post(
        "/api/v1/reviews", headers=admin_headers, json={"decision": "CONFIRMED"}
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


async def test_review_unknown_observation_404(client, admin_headers):
    response = await client.post(
        "/api/v1/reviews",
        headers=admin_headers,
        json={"observation_id": str(uuid.uuid4()), "decision": "CONFIRMED"},
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


async def test_defect_only_confirm_updates_defect_status(client, admin_headers, database):
    chain = await seed_observation_chain(database, with_defect=True)
    response = await client.post(
        "/api/v1/reviews",
        headers=admin_headers,
        json={"defect_id": str(chain.defect_id), "decision": "CONFIRMED"},
    )
    assert response.status_code == 201, response.text
    defect = await client.get(f"/api/v1/defects/{chain.defect_id}", headers=admin_headers)
    assert defect.status_code == 200
    assert defect.json()["status"] == "CONFIRMED"


async def test_confirmed_review_creates_training_example(client, admin_headers, database):
    chain = await seed_observation_chain(database, with_image=True)
    response = await client.post(
        "/api/v1/reviews",
        headers=admin_headers,
        json={"observation_id": str(chain.observation_id), "decision": "CONFIRMED"},
    )
    assert response.status_code == 201, response.text
    review_id = response.json()["id"]
    example = await _training_example(database, chain.observation_id)
    assert example is not None
    assert str(example.review_id) == review_id
    assert example.image_storage_key == chain.image_storage_key
    assert example.label["object_type"] == "telecom_well"
    assert example.label["condition"] == "damaged_cover"
    assert example.label["severity"] == 4
    assert example.label["review_decision"] == "CONFIRMED"


async def test_review_workflow_with_explicit_reviewed_at(client, admin_headers, database):
    chain = await seed_observation_chain(database)
    confirmed = await client.post(
        "/api/v1/reviews",
        headers=admin_headers,
        json={
            "observation_id": str(chain.observation_id),
            "decision": "CONFIRMED",
            "reviewed_at": _NAIVE_REVIEWED_AT,
        },
    )
    assert confirmed.status_code == 201, confirmed.text
    assert confirmed.json()["reviewer_id"] == str(await _admin_id(database))
    observation = await _get_observation(client, admin_headers, chain.observation_id)
    assert observation["review_status"] == "CONFIRMED"
    assert observation["effective_asset_type"] == "telecom_well"
    assert observation["effective_condition"] == "damaged_cover"
    assert observation["effective_severity"] == 4
    assert observation["condition_class"] == "damaged_cover"
    assert observation["severity"] == 4

    corrected = await client.post(
        "/api/v1/reviews",
        headers=admin_headers,
        json={
            "observation_id": str(chain.observation_id),
            "decision": "CORRECTED",
            "corrected_severity": 2,
            "corrected_condition": "ok",
            "reviewed_at": "2026-11-15T12:01:00",
        },
    )
    assert corrected.status_code == 201, corrected.text
    observation = await _get_observation(client, admin_headers, chain.observation_id)
    assert observation["review_status"] == "CORRECTED"
    assert observation["effective_severity"] == 2
    assert observation["effective_condition"] == "ok"
    assert observation["severity"] == 4

    asset = await client.get(f"/api/v1/assets/{chain.asset_id}", headers=admin_headers)
    assert asset.status_code == 200
    assert asset.json()["current_severity"] == 2
    assert asset.json()["current_condition"] == "ok"

    listing = await client.get(
        "/api/v1/reviews",
        headers=admin_headers,
        params={"observation_id": str(chain.observation_id)},
    )
    assert listing.status_code == 200
    assert listing.json()["total"] == 2
    assert corrected.json()["id"] != confirmed.json()["id"]

    example = await _training_example(database, chain.observation_id)
    assert example is not None
    assert str(example.review_id) == corrected.json()["id"]
    assert example.image_storage_key == chain.image_storage_key
    assert example.label["review_decision"] == "CORRECTED"
    assert example.label["severity"] == 2


async def test_rejected_review_with_explicit_reviewed_at(client, admin_headers, database):
    chain = await seed_observation_chain(database)
    response = await client.post(
        "/api/v1/reviews",
        headers=admin_headers,
        json={
            "observation_id": str(chain.observation_id),
            "decision": "REJECTED",
            "reviewed_at": _NAIVE_REVIEWED_AT,
        },
    )
    assert response.status_code == 201, response.text
    observation = await _get_observation(client, admin_headers, chain.observation_id)
    assert observation["review_status"] == "REJECTED"
    asset = await client.get(f"/api/v1/assets/{chain.asset_id}", headers=admin_headers)
    assert asset.json()["current_severity"] == 4


async def test_defect_only_confirm_with_explicit_reviewed_at(client, admin_headers, database):
    chain = await seed_observation_chain(database, with_defect=True)
    response = await client.post(
        "/api/v1/reviews",
        headers=admin_headers,
        json={
            "defect_id": str(chain.defect_id),
            "decision": "CONFIRMED",
            "reviewed_at": _NAIVE_REVIEWED_AT,
        },
    )
    assert response.status_code == 201, response.text
    defect = await client.get(f"/api/v1/defects/{chain.defect_id}", headers=admin_headers)
    assert defect.status_code == 200
    assert defect.json()["status"] == "CONFIRMED"


async def test_training_example_after_confirmed_explicit_reviewed_at(
    client, admin_headers, database
):
    chain = await seed_observation_chain(database, with_image=True)
    response = await client.post(
        "/api/v1/reviews",
        headers=admin_headers,
        json={
            "observation_id": str(chain.observation_id),
            "decision": "CONFIRMED",
            "reviewed_at": _NAIVE_REVIEWED_AT,
        },
    )
    assert response.status_code == 201, response.text
    example = await _training_example(database, chain.observation_id)
    assert example is not None
    assert str(example.review_id) == response.json()["id"]
    assert example.image_storage_key == chain.image_storage_key
    assert example.label["object_type"] == "telecom_well"
    assert example.label["condition"] == "damaged_cover"
    assert example.label["severity"] == 4
    assert example.label["review_decision"] == "CONFIRMED"
