"""Stage-4 RBAC matrix: every mutating endpoint x every role, plus read access.

VIEWER is read-only (403 on all mutations); OPERATOR, SERVICE and ADMIN may
mutate; all four roles may read lists, map layers, analytics, exports and ML
management endpoints. Resources are seeded minimally per case; upload delete
additionally respects ownership (seeded per acting user).
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

import httpx
import pytest
from app.config import Settings
from app.core.security import hash_password
from app.domain.enums import JobStatus, MediaType, UserRole
from app.infrastructure.database.models.upload import Upload
from app.infrastructure.database.models.user import User
from app.infrastructure.database.session import Database

from tests.api.test_assets_api import (
    seed_asset,
    seed_job,
    seed_observation_chain,
    seed_upload,
)
from tests.fixtures.media import make_jpeg_bytes

pytestmark = pytest.mark.api

_PASSWORD_HASH = hash_password("user-test-password")


@pytest.fixture(autouse=True)
def _ensure_database_setup(database: Database) -> None:
    """Pull the session-scoped database into the fixture closure so it is set
    up before clean_tables resolves it dynamically inside a running loop."""


_ROLES = ["VIEWER", "OPERATOR", "ADMIN", "SERVICE"]

_MUTATIONS = [
    "post_uploads",
    "post_jobs",
    "post_reviews",
    "post_routes",
    "patch_asset",
    "patch_defect",
    "delete_upload",
    "retry_job",
    "cancel_job",
]

_ALLOWED_STATUS = {
    "post_uploads": 201,
    "post_jobs": 201,
    "post_reviews": 201,
    "post_routes": 201,
    "patch_asset": 200,
    "patch_defect": 200,
    "delete_upload": 204,
    "retry_job": 200,
    "cancel_job": 200,
}

_CANCEL_BUG = (
    "BUG: JobService.cancel_job flushes without refreshing the job "
    "(app/application/services/jobs.py:157); updated_at has server-side "
    "onupdate=func.now() (app/infrastructure/database/base.py:35) so the attribute "
    "is expired after flush, and JobResponse.model_validate in the router "
    "(app/api/v1/jobs.py:265) reads it outside a greenlet -> MissingGreenlet -> 500 "
    "on every successful cancel. Expected: 200 with status CANCELLED."
)

_MUTATION_PARAMS = [
    pytest.param(role, case, id=f"{case}-{role}") for case in _MUTATIONS for role in _ROLES
]

_READS: list[tuple[str, dict[str, Any]]] = [
    ("/api/v1/uploads", {}),
    ("/api/v1/jobs", {}),
    ("/api/v1/assets", {}),
    ("/api/v1/observations", {}),
    ("/api/v1/defects", {}),
    ("/api/v1/routes", {}),
    ("/api/v1/reviews", {}),
    ("/api/v1/assets/nearby", {"longitude": 37.6173, "latitude": 55.7558, "radius_m": 100}),
    ("/api/v1/map/assets", {}),
    ("/api/v1/map/defects", {}),
    ("/api/v1/map/observations", {}),
    ("/api/v1/map/routes", {}),
    ("/api/v1/analytics/overview", {}),
    ("/api/v1/analytics/defects", {}),
    ("/api/v1/analytics/coverage", {}),
    ("/api/v1/exports/assets", {"format": "csv"}),
    ("/api/v1/exports/observations", {"format": "csv"}),
    ("/api/v1/exports/defects", {"format": "csv"}),
    ("/api/v1/ml/health", {}),
    ("/api/v1/ml/model-info", {}),
]


async def _role_headers(
    client: httpx.AsyncClient, database: Database, role: str
) -> tuple[uuid.UUID, dict[str, str]]:
    username = f"matrix-{role.lower()}-{uuid.uuid4().hex[:8]}"
    async with database.session() as session:
        user = User(
            username=username,
            password_hash=_PASSWORD_HASH,
            role=UserRole(role),
            is_active=True,
        )
        session.add(user)
        await session.commit()
        user_id = user.id
    login = await client.post(
        "/api/v1/auth/login", json={"username": username, "password": "user-test-password"}
    )
    assert login.status_code == 200, login.text
    return user_id, {"Authorization": f"Bearer {login.json()['access_token']}"}


async def _seed_owned_upload(database: Database, user_id: uuid.UUID) -> uuid.UUID:
    async with database.session() as session:
        upload = Upload(
            original_filename="owned.jpg",
            storage_key=f"uploads/{uuid.uuid4()}/owned.jpg",
            content_type="image/jpeg",
            file_size=128,
            checksum_sha256=uuid.uuid4().hex + uuid.uuid4().hex,
            media_type=MediaType.IMAGE,
            metadata_={},
            uploaded_by=user_id,
        )
        session.add(upload)
        await session.commit()
        return upload.id


async def _mutation_request(
    client: httpx.AsyncClient,
    database: Database,
    headers: dict[str, str],
    user_id: uuid.UUID,
    case: str,
) -> httpx.Response:
    if case == "post_uploads":
        return await client.post(
            "/api/v1/uploads",
            headers=headers,
            files={"file": ("frame.jpg", make_jpeg_bytes(seed=700), "image/jpeg")},
        )
    if case == "post_jobs":
        upload_id = await seed_upload(database)
        return await client.post(
            "/api/v1/jobs", headers=headers, json={"upload_id": str(upload_id)}
        )
    if case == "post_reviews":
        chain = await seed_observation_chain(database)
        return await client.post(
            "/api/v1/reviews",
            headers=headers,
            json={"observation_id": str(chain.observation_id), "decision": "CONFIRMED"},
        )
    if case == "post_routes":
        return await client.post(
            "/api/v1/routes",
            headers=headers,
            json={"name": "matrix route", "track": [[37.6173, 55.7558], [37.6180, 55.7560]]},
        )
    if case == "patch_asset":
        asset_id = await seed_asset(database)
        return await client.patch(
            f"/api/v1/assets/{asset_id}", headers=headers, json={"display_name": "matrix"}
        )
    if case == "patch_defect":
        chain = await seed_observation_chain(database, with_defect=True)
        return await client.patch(
            f"/api/v1/defects/{chain.defect_id}", headers=headers, json={"status": "CONFIRMED"}
        )
    if case == "delete_upload":
        upload_id = await _seed_owned_upload(database, user_id)
        return await client.delete(f"/api/v1/uploads/{upload_id}", headers=headers)
    if case == "retry_job":
        seeded = await seed_job(database, status=JobStatus.FAILED)
        return await client.post(f"/api/v1/jobs/{seeded.job_id}/retry", headers=headers)
    if case == "cancel_job":
        seeded = await seed_job(database, status=JobStatus.QUEUED)
        return await client.post(f"/api/v1/jobs/{seeded.job_id}/cancel", headers=headers)
    raise AssertionError(f"unknown mutation case {case}")


@pytest.mark.parametrize(("role", "case"), _MUTATION_PARAMS)
async def test_mutation_rbac(
    client: httpx.AsyncClient, database: Database, role: str, case: str
) -> None:
    user_id, headers = await _role_headers(client, database, role)
    response = await _mutation_request(client, database, headers, user_id, case)
    if role == "VIEWER":
        assert response.status_code == 403, response.text
        assert response.json()["error"]["code"] == "permission_denied"
    else:
        assert response.status_code == _ALLOWED_STATUS[case], response.text


@pytest.mark.parametrize("role", _ROLES)
@pytest.mark.parametrize(("path", "params"), _READS, ids=[path for path, _ in _READS])
async def test_read_access_for_all_roles(
    client: httpx.AsyncClient, database: Database, role: str, path: str, params: dict[str, Any]
) -> None:
    _, headers = await _role_headers(client, database, role)
    response = await client.get(path, headers=headers, params=params)
    assert response.status_code == 200, response.text


async def test_service_role_can_read_media_urls(
    client: httpx.AsyncClient, database: Database, settings: Settings
) -> None:
    _, headers = await _role_headers(client, database, "SERVICE")
    chain = await seed_observation_chain(database)
    assert chain.image_storage_key is not None
    image_path = Path(settings.storage_local_path) / chain.image_storage_key
    image_path.parent.mkdir(parents=True, exist_ok=True)
    image_path.write_bytes(make_jpeg_bytes(seed=701))
    response = await client.get(f"/api/v1/observations/{chain.observation_id}", headers=headers)
    assert response.status_code == 200
    assert response.json()["image_url"] is not None


async def test_unauthenticated_mutations_rejected(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/api/v1/routes", json={"name": "anon", "track": [[37.6, 55.7], [37.61, 55.71]]}
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "authentication_failed"
    listing = await client.get("/api/v1/assets")
    assert listing.status_code == 401


async def test_inactive_user_token_rejected(client: httpx.AsyncClient, database: Database) -> None:
    user_id, headers = await _role_headers(client, database, "OPERATOR")
    async with database.session() as session:
        user = await session.get(User, user_id)
        assert user is not None
        user.is_active = False
        await session.commit()
    response = await client.get("/api/v1/assets", headers=headers)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "authentication_failed"
