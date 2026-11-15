"""Health, readiness and Prometheus metrics endpoints."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.api


async def test_health_live(client):
    response = await client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_health_ready_components_ok(client):
    response = await client.get("/health/ready")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "ok"
    for component in ("database", "redis", "storage"):
        assert body["components"][component]["status"] == "ok", component


async def test_health_aggregate(client):
    response = await client.get("/health")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] in ("ok", "degraded")
    assert body["service"]
    assert body["version"]
    assert body["environment"] == "test"
    assert body["components"]["database"]["status"] == "ok"


async def test_metrics_exposes_http_or_pipeline_metrics(client):
    await client.get("/health")
    response = await client.get("/metrics")
    assert response.status_code == 200
    text = response.text
    assert "http_requests_total" in text or "pipeline_" in text
