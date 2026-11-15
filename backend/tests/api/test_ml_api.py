"""ML management API: provider health and model info (mock provider in tests)."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.api


async def test_ml_health_ok_mock(client, admin_headers):
    response = await client.get("/api/v1/ml/health", headers=admin_headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "ok"
    assert body["provider"] == "mock"
    assert body["model_loaded"] is True


async def test_ml_model_info(client, admin_headers):
    response = await client.get("/api/v1/ml/model-info", headers=admin_headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["name"] == "mock-infrastructure-detector"
    assert isinstance(body["version"], str) and body["version"]
    assert body["schema_version"] == "1.0"


async def test_ml_requires_auth(client):
    response = await client.get("/api/v1/ml/health")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "authentication_failed"
