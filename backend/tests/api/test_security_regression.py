"""Stage-4 security regression suite against the real API + PostgreSQL/Redis.

Locks the wave-1 security fixes: JWT tamper/alg-none/role-claim escalation and
logout revocation (SEC-7), upload ownership and shared-registry semantics
(SEC-8), VIEWER media gating, redacted cross-user dedup, idempotency
fingerprints (API-6/7), pre-auth body limits (SEC-1/2), security headers and
request-id truncation (SEC-13/19), non-finite coordinates, CSV injection via
PATCH (SEC-11), per-username login throttle (SEC-6) and metrics cardinality
(SEC-12).
"""

from __future__ import annotations

import base64
import csv
import io
import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from app.config import Settings
from app.core.security import create_access_token, hash_password
from app.domain.enums import UserRole
from app.infrastructure.database.models.user import User
from app.infrastructure.database.session import Database
from fastapi import FastAPI
from sqlalchemy import select

from tests.api.test_assets_api import seed_asset, seed_observation_chain, seed_upload_with_file
from tests.fixtures.media import make_jpeg_bytes, upload_metadata
from tests.fixtures.ml_stub import StubMLProvider

pytestmark = pytest.mark.api


@pytest.fixture(autouse=True)
def _ensure_database_setup(database: Database) -> None:
    """Pull the session-scoped database into the fixture closure so it is set
    up before clean_tables resolves it dynamically inside a running loop."""


async def _login(client: httpx.AsyncClient, username: str, password: str) -> dict[str, str]:
    response = await client.post(
        "/api/v1/auth/login", json={"username": username, "password": password}
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def _make_user(
    client: httpx.AsyncClient, database: Database, username: str, role: str
) -> tuple[uuid.UUID, dict[str, str]]:
    async with database.session() as session:
        user = User(
            username=username,
            password_hash=hash_password("user-test-password"),
            role=UserRole(role),
            is_active=True,
        )
        session.add(user)
        await session.commit()
        user_id = user.id
    return user_id, await _login(client, username, "user-test-password")


async def _user_id(database: Database, username: str) -> uuid.UUID:
    async with database.session() as session:
        return (
            await session.execute(select(User.id).where(User.username == username))
        ).scalar_one()


async def _upload(
    client: httpx.AsyncClient,
    headers: dict[str, str],
    data: bytes,
    *,
    filename: str = "frame.jpg",
    metadata: dict[str, Any] | None = None,
    idempotency_key: str | None = None,
) -> httpx.Response:
    form: dict[str, str] = {}
    if metadata is not None:
        form["metadata"] = json.dumps(metadata)
    extra = dict(headers)
    if idempotency_key is not None:
        extra["Idempotency-Key"] = idempotency_key
    return await client.post(
        "/api/v1/uploads",
        headers=extra,
        files={"file": (filename, data, "image/jpeg")},
        data=form,
    )


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


async def test_tampered_signature_rejected(client: httpx.AsyncClient, admin_headers: dict) -> None:
    token = admin_headers["Authorization"].removeprefix("Bearer ")
    header, payload, signature = token.split(".")
    flipped = ("A" if signature[0] != "A" else "B") + signature[1:]
    tampered = f"{header}.{payload}.{flipped}"
    response = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {tampered}"})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "authentication_failed"


async def test_alg_none_token_rejected(
    client: httpx.AsyncClient, admin_headers: dict, database: Database
) -> None:
    admin_id = await _user_id(database, "admin")
    header = _b64url(json.dumps({"alg": "none", "typ": "JWT"}).encode())
    payload = _b64url(
        json.dumps(
            {
                "sub": str(admin_id),
                "role": "ADMIN",
                "type": "access",
                "jti": str(uuid.uuid4()),
                "exp": int((datetime.now(UTC) + timedelta(minutes=5)).timestamp()),
            }
        ).encode()
    )
    response = await client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {header}.{payload}."}
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "authentication_failed"


async def test_escalated_role_claim_does_not_grant_access(
    client: httpx.AsyncClient, viewer_headers: dict, database: Database, settings: Settings
) -> None:
    viewer_id = await _user_id(database, "viewer1")
    forged = create_access_token(
        subject=viewer_id,
        role="ADMIN",
        secret=settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
        expires_minutes=5,
    )
    response = await _upload(
        client, {"Authorization": f"Bearer {forged}"}, make_jpeg_bytes(seed=901)
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "permission_denied"


async def test_logout_revokes_token(client: httpx.AsyncClient, admin_headers: dict) -> None:
    logout = await client.post("/api/v1/auth/logout", headers=admin_headers)
    assert logout.status_code == 200, logout.text
    reuse = await client.get("/api/v1/auth/me", headers=admin_headers)
    assert reuse.status_code == 401
    assert reuse.json()["error"]["code"] == "authentication_failed"


@pytest.mark.parametrize("kind", ["garbage", "expired"])
async def test_garbage_and_expired_tokens_rejected(
    client: httpx.AsyncClient, settings: Settings, kind: str
) -> None:
    if kind == "garbage":
        token = "not-a-jwt-at-all"
    else:
        token = create_access_token(
            subject=uuid.uuid4(),
            role="ADMIN",
            secret=settings.jwt_secret_key,
            algorithm=settings.jwt_algorithm,
            expires_minutes=-5,
        )
    response = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "authentication_failed"


async def test_upload_delete_ownership(
    client: httpx.AsyncClient, database: Database, admin_headers: dict
) -> None:
    _, headers_a = await _make_user(client, database, "owner-a", "OPERATOR")
    _, headers_b = await _make_user(client, database, "owner-b", "OPERATOR")
    created = await _upload(client, headers_a, make_jpeg_bytes(seed=902))
    assert created.status_code == 201, created.text
    upload_id = created.json()["upload"]["id"]

    foreign_delete = await client.delete(f"/api/v1/uploads/{upload_id}", headers=headers_b)
    assert foreign_delete.status_code == 403
    assert foreign_delete.json()["error"]["code"] == "permission_denied"

    admin_delete = await client.delete(f"/api/v1/uploads/{upload_id}", headers=admin_headers)
    assert admin_delete.status_code == 204
    missing = await client.get(f"/api/v1/uploads/{upload_id}", headers=admin_headers)
    assert missing.status_code == 404


async def test_shared_registry_cross_operator_patch_allowed(
    client: httpx.AsyncClient, database: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "app.workers.tasks.processing.build_ml_provider", lambda settings: StubMLProvider()
    )
    _, headers_a = await _make_user(client, database, "registry-a", "OPERATOR")
    _, headers_b = await _make_user(client, database, "registry-b", "OPERATOR")
    created = await _upload(
        client, headers_a, make_jpeg_bytes(seed=903), metadata=upload_metadata()
    )
    assert created.status_code == 201, created.text
    job = await client.post(
        "/api/v1/jobs",
        headers=headers_a,
        json={"upload_id": created.json()["upload"]["id"]},
    )
    assert job.status_code == 201, job.text
    assert job.json()["status"] == "COMPLETED"
    assets = await client.get("/api/v1/assets", headers=headers_a)
    assert assets.json()["total"] == 1
    asset_id = assets.json()["items"][0]["id"]

    patched = await client.patch(
        f"/api/v1/assets/{asset_id}",
        headers=headers_b,
        json={"display_name": "renamed by another operator"},
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["display_name"] == "renamed by another operator"


async def test_viewer_media_gating_and_operator_file_access(
    client: httpx.AsyncClient,
    database: Database,
    operator_headers: dict,
    viewer_headers: dict,
) -> None:
    data = make_jpeg_bytes(seed=904)
    created = await _upload(client, operator_headers, data, metadata=upload_metadata())
    assert created.status_code == 201, created.text
    upload_id = created.json()["upload"]["id"]
    await seed_observation_chain(database)

    listing = await client.get("/api/v1/uploads", headers=viewer_headers)
    assert listing.status_code == 200
    assert listing.json()["total"] >= 1
    assert all(item["presigned_url"] is None for item in listing.json()["items"])
    assert any(item["id"] == upload_id for item in listing.json()["items"])
    detail = await client.get(f"/api/v1/uploads/{upload_id}", headers=viewer_headers)
    assert detail.status_code == 200
    assert detail.json()["presigned_url"] is None
    storage_key = detail.json()["storage_key"]

    observations = await client.get("/api/v1/observations", headers=viewer_headers)
    assert observations.status_code == 200
    assert observations.json()["total"] >= 1
    for item in observations.json()["items"]:
        assert item["image_url"] is None
        assert item["crop_url"] is None

    forbidden = await client.get(f"/api/v1/files/{storage_key}", headers=viewer_headers)
    assert forbidden.status_code == 403
    assert forbidden.json()["error"]["code"] == "permission_denied"

    allowed = await client.get(f"/api/v1/files/{storage_key}", headers=operator_headers)
    assert allowed.status_code == 200
    assert allowed.content == data


async def test_cross_user_dedup_is_redacted(client: httpx.AsyncClient, database: Database) -> None:
    _, headers_a = await _make_user(client, database, "dedup-a", "OPERATOR")
    _, headers_b = await _make_user(client, database, "dedup-b", "OPERATOR")
    data = make_jpeg_bytes(seed=905)
    metadata = upload_metadata()
    first = await _upload(client, headers_a, data, filename="secret-name.jpg", metadata=metadata)
    assert first.status_code == 201, first.text

    foreign = await _upload(client, headers_b, data, filename="other-name.jpg")
    assert foreign.status_code == 200, foreign.text
    body = foreign.json()
    assert body["created"] is False
    upload = body["upload"]
    assert upload["id"] == first.json()["upload"]["id"]
    assert upload["original_filename"] == "[redacted]"
    assert upload["storage_key"] == "[redacted]"
    assert upload["metadata"] == {}
    assert upload["uploaded_by"] is None
    assert upload["presigned_url"] is None

    owner_replay = await _upload(client, headers_a, data)
    assert owner_replay.status_code == 200
    owner_upload = owner_replay.json()["upload"]
    assert owner_replay.json()["created"] is False
    assert owner_upload["original_filename"] == "secret-name.jpg"
    assert owner_upload["metadata"] == metadata
    assert owner_upload["presigned_url"]


async def test_upload_idempotency_key_overlong_422(
    client: httpx.AsyncClient, admin_headers: dict
) -> None:
    response = await _upload(
        client, admin_headers, make_jpeg_bytes(seed=906), idempotency_key="k" * 129
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


async def test_jobs_idempotency_fingerprint_conflict_and_replay(
    client: httpx.AsyncClient, admin_headers: dict, database: Database, settings: Settings
) -> None:
    upload_a = await seed_upload_with_file(database, settings.storage_local_path, seed=907)
    upload_b = await seed_upload_with_file(database, settings.storage_local_path, seed=908)
    key = str(uuid.uuid4())
    headers = {**admin_headers, "Idempotency-Key": key}
    first = await client.post("/api/v1/jobs", headers=headers, json={"upload_id": str(upload_a)})
    assert first.status_code == 201, first.text
    conflict = await client.post("/api/v1/jobs", headers=headers, json={"upload_id": str(upload_b)})
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "idempotency_conflict"
    replay = await client.post("/api/v1/jobs", headers=headers, json={"upload_id": str(upload_a)})
    assert replay.status_code == first.status_code == 201
    assert replay.json()["id"] == first.json()["id"]


async def test_login_oversized_content_length_rejected_pre_auth(client: httpx.AsyncClient) -> None:
    request = client.build_request(
        "POST",
        "/api/v1/auth/login",
        json={"username": "admin", "password": "whatever"},
    )
    request.headers["Content-Length"] = str(3 * 1024 * 1024)
    response = await client.send(request)
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "payload_too_large"


async def test_login_oversized_json_body_413(client: httpx.AsyncClient) -> None:
    body = json.dumps({"username": "admin", "password": "x" * (3 * 1024 * 1024)})
    response = await client.post(
        "/api/v1/auth/login", content=body, headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "payload_too_large"


async def test_multipart_oversized_content_length_rejected_pre_auth(
    client: httpx.AsyncClient, settings: Settings
) -> None:
    request = client.build_request(
        "POST",
        "/api/v1/uploads",
        files={"file": ("frame.jpg", make_jpeg_bytes(seed=909), "image/jpeg")},
    )
    request.headers["Content-Length"] = str(settings.max_upload_size_bytes + 1024 * 1024 + 1)
    response = await client.send(request)
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "payload_too_large"


async def test_security_headers_on_api_responses(
    client: httpx.AsyncClient, admin_headers: dict
) -> None:
    for path in ("/api/v1/assets", "/health/live"):
        response = await client.get(path, headers=admin_headers)
        assert response.status_code == 200
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert response.headers["X-Frame-Options"] == "DENY"


async def test_request_id_echoed_and_truncated(
    client: httpx.AsyncClient, admin_headers: dict
) -> None:
    response = await client.get(
        "/api/v1/assets", headers={**admin_headers, "X-Request-ID": "r" * 100}
    )
    assert response.status_code == 200
    assert response.headers["x-request-id"] == "r" * 64


@pytest.mark.parametrize("field", ["longitude", "latitude"])
@pytest.mark.parametrize(
    "value", [float("nan"), float("inf"), float("-inf")], ids=["nan", "inf", "-inf"]
)
async def test_patch_location_non_finite_422(
    client: httpx.AsyncClient, admin_headers: dict, database: Database, field: str, value: float
) -> None:
    asset_id = await seed_asset(database)
    location = {"longitude": 37.6173, "latitude": 55.7558}
    location[field] = value
    response = await client.patch(
        f"/api/v1/assets/{asset_id}",
        headers={**admin_headers, "Content-Type": "application/json"},
        content=json.dumps({"location": location}, allow_nan=True),
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


@pytest.mark.parametrize("raw", ["nan", "inf", "-inf"])
async def test_nearby_non_finite_longitude_422(
    client: httpx.AsyncClient, admin_headers: dict, raw: str
) -> None:
    response = await client.get(
        "/api/v1/assets/nearby",
        headers=admin_headers,
        params={"longitude": raw, "latitude": 55.7558, "radius_m": 100},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


async def test_csv_injection_via_patch_is_escaped(
    client: httpx.AsyncClient, admin_headers: dict, database: Database
) -> None:
    asset_id = await seed_asset(database)
    payload = '=HYPERLINK("http://evil","x")'
    patched = await client.patch(
        f"/api/v1/assets/{asset_id}", headers=admin_headers, json={"display_name": payload}
    )
    assert patched.status_code == 200, patched.text
    export = await client.get(
        "/api/v1/exports/assets", headers=admin_headers, params={"format": "csv"}
    )
    assert export.status_code == 200
    rows = list(csv.reader(io.StringIO(export.content.decode("utf-8-sig"))))
    header = rows[0]
    assert rows[1][header.index("display_name")] == "'" + payload


async def test_login_per_username_throttle_across_ips(
    client: httpx.AsyncClient,
    app: FastAPI,
    database: Database,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    username = f"throttle-{uuid.uuid4().hex[:8]}"
    async with database.session() as session:
        session.add(
            User(
                username=username,
                password_hash=hash_password("user-test-password"),
                role=UserRole.OPERATOR,
                is_active=True,
            )
        )
        await session.commit()
    monkeypatch.setattr(settings, "rate_limit_login_per_username_per_minute", 3)
    bad = {"username": username, "password": "wrong-password"}
    for _ in range(3):
        response = await client.post("/api/v1/auth/login", json=bad)
        assert response.status_code == 401

    other_ip = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, client=("10.9.9.9", 4321)),
        base_url="http://testserver",
    )
    async with other_ip:
        throttled = await other_ip.post("/api/v1/auth/login", json=bad)
    assert throttled.status_code == 429
    assert throttled.json()["error"]["code"] == "rate_limited"
    assert int(throttled.headers["Retry-After"]) > 0


async def test_metrics_unmatched_path_uses_constant_label(client: httpx.AsyncClient) -> None:
    random_path = f"/api/v1/no-such-route-{uuid.uuid4().hex}"
    missing = await client.get(random_path)
    assert missing.status_code == 404
    metrics = await client.get("/metrics")
    assert metrics.status_code == 200
    assert "<unmatched>" in metrics.text
    assert random_path not in metrics.text
