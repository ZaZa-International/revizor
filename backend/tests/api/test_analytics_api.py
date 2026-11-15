"""Analytics API: overview counters, defect aggregation, grid coverage."""

from __future__ import annotations

import pytest

from tests.api.test_assets_api import seed_asset, seed_observation_chain

pytestmark = pytest.mark.api


async def test_overview_keys_and_counts(client, admin_headers, database):
    await seed_observation_chain(database, with_defect=True)
    await seed_asset(database, asset_type="pole")
    response = await client.get("/api/v1/analytics/overview", headers=admin_headers)
    assert response.status_code == 200
    body = response.json()
    for key in (
        "assets_total",
        "observations_total",
        "defects_total",
        "uploads_total",
        "routes_total",
        "observations_reviewed",
        "observations_reviewed_ratio",
        "assets_without_location",
        "assets_by_type",
        "assets_by_priority_band",
        "defects_by_status",
        "defects_by_severity",
        "jobs_by_status",
    ):
        assert key in body, key
    assert body["assets_total"] == 2
    assert body["observations_total"] == 1
    assert body["defects_total"] == 1
    assert body["uploads_total"] >= 1
    assert 0.0 <= body["observations_reviewed_ratio"] <= 1.0
    assert isinstance(body["assets_by_type"], list)
    assert all({"key", "count"} <= set(entry) for entry in body["assets_by_type"])


async def test_defects_by_type(client, admin_headers, database):
    await seed_observation_chain(database, with_defect=True)
    response = await client.get("/api/v1/analytics/defects", headers=admin_headers)
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body["by_type"], list)
    entry = next(item for item in body["by_type"] if item["defect_type"] == "damaged_cover")
    assert entry["count"] == 1
    assert entry["avg_severity"] == pytest.approx(4.0)
    assert entry["confirmed_count"] == 0
    assert body["open_high_severity_count"] == 1


async def test_coverage_grid_fields(client, admin_headers, database):
    await seed_observation_chain(database, lon=37.6173, lat=55.7558)
    response = await client.get("/api/v1/analytics/coverage", headers=admin_headers)
    assert response.status_code == 200
    body = response.json()
    for key in (
        "area_bbox",
        "grid_cell_m",
        "grid_cols",
        "grid_rows",
        "total_cells",
        "covered_cells",
        "coverage_ratio",
        "gap_cells",
    ):
        assert key in body, key
    assert body["total_cells"] >= body["covered_cells"] >= 1
    assert 0.0 <= body["coverage_ratio"] <= 1.0
    assert body["gap_cells"] == body["total_cells"] - body["covered_cells"]
