"""Exports API: CSV/XLSX rendering, headers, columns, format validation."""

from __future__ import annotations

import csv
import io

import pytest

from tests.api.test_assets_api import seed_asset, seed_observation_chain

pytestmark = pytest.mark.api


def _csv_rows(content: bytes) -> list[list[str]]:
    text = content.decode("utf-8-sig")
    return list(csv.reader(io.StringIO(text)))


async def test_export_assets_csv(client, admin_headers, database):
    await seed_asset(database, asset_type="telecom_well", lon=37.6173, lat=55.7558)
    await seed_asset(database, asset_type="pole")
    response = await client.get(
        "/api/v1/exports/assets", headers=admin_headers, params={"format": "csv"}
    )
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/csv")
    assert "attachment" in response.headers["content-disposition"]
    rows = _csv_rows(response.content)
    header = rows[0]
    assert "id" in header
    assert "asset_type" in header
    assert len(rows) == 3
    asset_types = {row[header.index("asset_type")] for row in rows[1:]}
    assert asset_types == {"telecom_well", "pole"}


async def test_export_assets_xlsx(client, admin_headers, database):
    await seed_asset(database)
    response = await client.get(
        "/api/v1/exports/assets", headers=admin_headers, params={"format": "xlsx"}
    )
    assert response.status_code == 200
    assert response.content[:2] == b"PK"
    assert "spreadsheetml" in response.headers["content-type"]


async def test_export_defects_csv_columns(client, admin_headers, database):
    chain = await seed_observation_chain(database, with_defect=True)
    response = await client.get(
        "/api/v1/exports/defects", headers=admin_headers, params={"format": "csv"}
    )
    assert response.status_code == 200
    rows = _csv_rows(response.content)
    header = rows[0]
    assert "observation_count" in header
    assert "asset_type" in header
    assert len(rows) == 2
    row = rows[1]
    assert row[header.index("id")] == str(chain.defect_id)
    assert row[header.index("asset_type")] == "telecom_well"
    assert row[header.index("observation_count")] == "1"


async def test_export_observations_csv(client, admin_headers, database):
    chain = await seed_observation_chain(database)
    response = await client.get(
        "/api/v1/exports/observations", headers=admin_headers, params={"format": "csv"}
    )
    assert response.status_code == 200
    rows = _csv_rows(response.content)
    header = rows[0]
    assert "id" in header
    assert "processing_job_id" in header
    assert len(rows) == 2
    assert rows[1][header.index("id")] == str(chain.observation_id)
    assert rows[1][header.index("processing_job_id")] == str(chain.job_id)


async def test_export_invalid_format_422(client, admin_headers):
    response = await client.get(
        "/api/v1/exports/assets", headers=admin_headers, params={"format": "pdf"}
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
