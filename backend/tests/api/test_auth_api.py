"""Auth API: login, /me, token validation and RBAC enforcement."""

from __future__ import annotations

import uuid

import pytest
from app.core.security import create_access_token

from tests.fixtures.media import make_jpeg_bytes

pytestmark = pytest.mark.api


def _error(response) -> dict:
    body = response.json()
    assert set(body) == {"error"}
    error = body["error"]
    assert isinstance(error["code"], str)
    assert isinstance(error["message"], str)
    assert isinstance(error["details"], list)
    return error


async def test_login_ok_returns_token_and_user(client):
    response = await client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "admin-test-password"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert isinstance(body["access_token"], str) and body["access_token"]
    assert body["token_type"] == "bearer"
    assert body["expires_in_minutes"] > 0
    assert body["user"]["username"] == "admin"
    assert body["user"]["role"] == "ADMIN"
    assert body["user"]["is_active"] is True
    uuid.UUID(body["user"]["id"])


async def test_login_wrong_password_401_envelope(client):
    response = await client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "definitely-wrong"},
    )
    assert response.status_code == 401
    error = _error(response)
    assert error["code"] == "authentication_failed"
    assert error["message"]


async def test_me_with_token(client, admin_headers):
    response = await client.get("/api/v1/auth/me", headers=admin_headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["username"] == "admin"
    assert body["role"] == "ADMIN"
    uuid.UUID(body["id"])


async def test_me_without_token_401(client):
    response = await client.get("/api/v1/auth/me")
    assert response.status_code == 401
    assert _error(response)["code"] == "authentication_failed"


async def test_viewer_cannot_upload(client, viewer_headers):
    response = await client.post(
        "/api/v1/uploads",
        headers=viewer_headers,
        files={"file": ("frame.jpg", make_jpeg_bytes(seed=1), "image/jpeg")},
    )
    assert response.status_code == 403
    assert _error(response)["code"] == "permission_denied"


async def test_viewer_cannot_review(client, viewer_headers):
    response = await client.post(
        "/api/v1/reviews",
        headers=viewer_headers,
        json={"observation_id": str(uuid.uuid4()), "decision": "CONFIRMED"},
    )
    assert response.status_code == 403
    assert _error(response)["code"] == "permission_denied"


async def test_invalid_token_401(client):
    response = await client.get("/api/v1/auth/me", headers={"Authorization": "Bearer not-a-jwt"})
    assert response.status_code == 401
    assert _error(response)["code"] == "authentication_failed"


async def test_expired_token_401(client, settings):
    token = create_access_token(
        subject=uuid.uuid4(),
        role="ADMIN",
        secret=settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
        expires_minutes=-5,
    )
    response = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401
    assert _error(response)["code"] == "authentication_failed"


async def test_valid_token_unknown_user_401(client, settings):
    token = create_access_token(
        subject=uuid.uuid4(),
        role="ADMIN",
        secret=settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
        expires_minutes=5,
    )
    response = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401
    assert _error(response)["code"] == "authentication_failed"
