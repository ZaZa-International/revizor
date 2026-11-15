"""Map API: GeoJSON FeatureCollection layers for assets, defects, observations, routes."""

from __future__ import annotations

import uuid
from datetime import datetime

import pytest
from app.infrastructure.database.models.route import Route
from geoalchemy2 import WKTElement

from tests.api.test_assets_api import seed_asset, seed_observation_chain

pytestmark = pytest.mark.api


def _assert_feature_collection(body: dict) -> list[dict]:
    assert body["type"] == "FeatureCollection"
    assert isinstance(body["features"], list)
    for feature in body["features"]:
        assert feature["type"] == "Feature"
        assert isinstance(feature["properties"], dict)
    return body["features"]


async def test_map_assets_feature_collection_lonlat_order(client, admin_headers, database):
    asset_id = await seed_asset(
        database, lon=37.6173, lat=55.7558, priority_band=None, display_name="Map well"
    )
    response = await client.get("/api/v1/map/assets", headers=admin_headers)
    assert response.status_code == 200
    features = _assert_feature_collection(response.json())
    assert len(features) == 1
    feature = features[0]
    assert feature["geometry"]["type"] == "Point"
    lon, lat = feature["geometry"]["coordinates"]
    assert lon == pytest.approx(37.6173)
    assert lat == pytest.approx(55.7558)
    assert feature["properties"]["id"] == str(asset_id)
    assert "priority_band" in feature["properties"]
    assert feature["properties"]["asset_type"] == "telecom_well"


async def test_map_assets_bbox_excludes_outside(client, admin_headers, database):
    inside_id = await seed_asset(database, lon=37.6173, lat=55.7558)
    await seed_asset(database, lon=37.95, lat=55.95)
    response = await client.get(
        "/api/v1/map/assets",
        headers=admin_headers,
        params={"bbox": "37.6,55.7,37.7,55.8"},
    )
    assert response.status_code == 200
    features = _assert_feature_collection(response.json())
    assert len(features) == 1
    assert features[0]["properties"]["id"] == str(inside_id)


async def test_map_defects_feature_collection(client, admin_headers, database):
    chain = await seed_observation_chain(database, with_defect=True, lon=37.6173, lat=55.7558)
    response = await client.get("/api/v1/map/defects", headers=admin_headers)
    assert response.status_code == 200
    features = _assert_feature_collection(response.json())
    assert len(features) == 1
    properties = features[0]["properties"]
    assert properties["id"] == str(chain.defect_id)
    assert properties["asset_id"] == str(chain.asset_id)
    assert properties["defect_type"] == "damaged_cover"
    assert properties["severity"] == 4
    assert properties["status"] == "OPEN"
    lon, lat = features[0]["geometry"]["coordinates"]
    assert lon == pytest.approx(37.6173)
    assert lat == pytest.approx(55.7558)


async def test_map_observations_feature_collection(client, admin_headers, database):
    chain = await seed_observation_chain(database, lon=37.6173, lat=55.7558)
    response = await client.get("/api/v1/map/observations", headers=admin_headers)
    assert response.status_code == 200
    features = _assert_feature_collection(response.json())
    assert len(features) == 1
    properties = features[0]["properties"]
    assert properties["id"] == str(chain.observation_id)
    assert properties["processing_job_id"] == str(chain.job_id)
    lon, lat = features[0]["geometry"]["coordinates"]
    assert lon == pytest.approx(37.6173)
    assert lat == pytest.approx(55.7558)


async def test_map_routes_linestring(client, admin_headers, database):
    route_id = uuid.uuid4()
    async with database.session() as session:
        session.add(
            Route(
                id=route_id,
                name="Test route",
                vehicle_id="veh-1",
                started_at=datetime(2026, 11, 15, 12, 0),
                track_geometry=WKTElement(
                    "LINESTRING(37.6173 55.7558, 37.6200 55.7560, 37.6230 55.7565)",
                    srid=4326,
                ),
                total_distance_m=400.0,
                metadata_={},
            )
        )
        await session.commit()
    response = await client.get("/api/v1/map/routes", headers=admin_headers)
    assert response.status_code == 200
    features = _assert_feature_collection(response.json())
    assert len(features) == 1
    feature = features[0]
    assert feature["properties"]["id"] == str(route_id)
    assert feature["properties"]["name"] == "Test route"
    geometry = feature["geometry"]
    assert geometry["type"] == "LineString"
    assert len(geometry["coordinates"]) == 3
    first_lon, first_lat = geometry["coordinates"][0]
    assert first_lon == pytest.approx(37.6173)
    assert first_lat == pytest.approx(55.7558)
