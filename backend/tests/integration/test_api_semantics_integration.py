"""Wave-1 API semantics against real PostgreSQL/PostGIS + Redis + local storage:
idempotency fingerprints, patch presence, defect transitions, review validation,
pagination envelopes, sort/date 422s, export truncation/escaping, batch N+1 fixes."""

from __future__ import annotations

import csv
import hashlib
import io
import os
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from app.domain.enums import (
    AuditAction,
    ConditionChangeSource,
    MediaType,
    ReviewDecision,
)
from app.infrastructure.database.models.history import AssetConditionHistory
from app.infrastructure.database.models.idempotency import IdempotencyRecord
from app.infrastructure.database.models.job import ProcessingJob
from app.infrastructure.database.models.route import Route
from app.infrastructure.database.models.upload import Upload
from app.infrastructure.database.models.user import AuditLog
from app.infrastructure.database.repositories.uploads import UploadRepository
from app.schemas.assets import ReviewCreateRequest
from sqlalchemy import event, select, update

from tests.api.test_assets_api import seed_asset, seed_observation_chain
from tests.fixtures.media import make_jpeg_bytes

# Each test re-logins as admin (users are truncated per test); the SEC-6
# per-username throttle must not bite the test suite (conftest parity).
os.environ.setdefault("RATE_LIMIT_LOGIN_PER_USERNAME_PER_MINUTE", "10000")

pytestmark = pytest.mark.integration


def _write_physical_image(settings, storage_key: str) -> None:
    path = Path(settings.storage_local_path) / storage_key
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(make_jpeg_bytes(seed=7))


class TestIdempotencyApi:
    async def test_review_replay_and_fingerprint_conflict(self, client, admin_headers, database):
        chain = await seed_observation_chain(database)
        body = {"observation_id": str(chain.observation_id), "decision": "CONFIRMED"}
        headers = {**admin_headers, "Idempotency-Key": "review-key-1"}
        first = await client.post("/api/v1/reviews", headers=headers, json=body)
        assert first.status_code == 201, first.text
        replay = await client.post("/api/v1/reviews", headers=headers, json=body)
        assert replay.status_code == 201
        assert replay.json()["id"] == first.json()["id"]
        conflict = await client.post(
            "/api/v1/reviews", headers=headers, json={**body, "comment": "different payload"}
        )
        assert conflict.status_code == 409
        assert conflict.json()["error"]["code"] == "idempotency_conflict"

    async def test_request_hash_persisted(self, client, admin_headers, database):
        chain = await seed_observation_chain(database)
        body = {"observation_id": str(chain.observation_id), "decision": "CONFIRMED"}
        response = await client.post(
            "/api/v1/reviews",
            headers={**admin_headers, "Idempotency-Key": "hash-key"},
            json=body,
        )
        assert response.status_code == 201
        expected = hashlib.sha256(
            ReviewCreateRequest(
                observation_id=chain.observation_id, decision=ReviewDecision.CONFIRMED
            )
            .model_dump_json()
            .encode()
        ).hexdigest()
        async with database.session() as session:
            record = (
                await session.execute(
                    select(IdempotencyRecord).where(IdempotencyRecord.key == "hash-key")
                )
            ).scalar_one()
        assert record.request_hash == expected

    @pytest.mark.parametrize(
        ("path", "body"),
        [
            ("/api/v1/reviews", {"decision": "CONFIRMED", "defect_id": str(uuid.uuid4())}),
            ("/api/v1/jobs", {"upload_id": str(uuid.uuid4())}),
            ("/api/v1/routes", {"name": "r"}),
        ],
    )
    async def test_overlong_key_422(self, client, admin_headers, path, body):
        response = await client.post(
            path, headers={**admin_headers, "Idempotency-Key": "k" * 129}, json=body
        )
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "validation_error"


class TestAssetPatchSemantics:
    async def test_reason_only_patch(self, client, admin_headers, database):
        asset_id = await seed_asset(database)
        response = await client.patch(
            f"/api/v1/assets/{asset_id}",
            headers=admin_headers,
            json={"priority_override_reason": "storm damage"},
        )
        assert response.status_code == 200, response.text
        assert response.json()["priority_override_reason"] == "storm damage"
        assert response.json()["version"] == 2

    async def test_override_set_then_clear_also_clears_reason(
        self, client, admin_headers, database
    ):
        asset_id = await seed_asset(database)
        set_response = await client.patch(
            f"/api/v1/assets/{asset_id}",
            headers=admin_headers,
            json={"priority_override": 90, "priority_override_reason": "urgent"},
        )
        assert set_response.status_code == 200, set_response.text
        assert set_response.json()["current_priority"] == 90
        clear_response = await client.patch(
            f"/api/v1/assets/{asset_id}",
            headers=admin_headers,
            json={"priority_override": None},
        )
        assert clear_response.status_code == 200, clear_response.text
        body = clear_response.json()
        assert body["priority_override"] is None
        assert body["priority_override_reason"] is None


class TestDefectTransitionsApi:
    async def test_resolve_reopen_reject_terminal(self, client, admin_headers, database):
        chain = await seed_observation_chain(database, with_defect=True)
        url = f"/api/v1/defects/{chain.defect_id}"
        resolved = await client.patch(url, headers=admin_headers, json={"status": "RESOLVED"})
        assert resolved.status_code == 200, resolved.text
        assert resolved.json()["resolved_at"] is not None
        reopened = await client.patch(url, headers=admin_headers, json={"status": "OPEN"})
        assert reopened.status_code == 200, reopened.text
        assert reopened.json()["resolved_at"] is None
        rejected = await client.patch(url, headers=admin_headers, json={"status": "REJECTED"})
        assert rejected.status_code == 200, rejected.text
        terminal = await client.patch(url, headers=admin_headers, json={"status": "RESOLVED"})
        assert terminal.status_code == 422
        assert terminal.json()["error"]["code"] == "validation_error"

    async def test_confirmed_to_open_invalid(self, client, admin_headers, database):
        chain = await seed_observation_chain(database, with_defect=True)
        url = f"/api/v1/defects/{chain.defect_id}"
        assert (
            await client.patch(url, headers=admin_headers, json={"status": "CONFIRMED"})
        ).status_code == 200
        invalid = await client.patch(url, headers=admin_headers, json={"status": "OPEN"})
        assert invalid.status_code == 422

    async def test_explicit_null_description_clears(self, client, admin_headers, database):
        chain = await seed_observation_chain(database, with_defect=True)
        url = f"/api/v1/defects/{chain.defect_id}"
        await client.patch(url, headers=admin_headers, json={"description": "cracked lid"})
        cleared = await client.patch(url, headers=admin_headers, json={"description": None})
        assert cleared.status_code == 200, cleared.text
        assert cleared.json()["description"] is None


class TestReviewValidationApi:
    async def test_bogus_condition_422(self, client, admin_headers, database):
        chain = await seed_observation_chain(database)
        response = await client.post(
            "/api/v1/reviews",
            headers=admin_headers,
            json={
                "observation_id": str(chain.observation_id),
                "decision": "CORRECTED",
                "corrected_condition": "totally_bogus",
            },
        )
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "validation_error"

    async def test_future_reviewed_at_422(self, client, admin_headers, database):
        chain = await seed_observation_chain(database)
        future = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
        response = await client.post(
            "/api/v1/reviews",
            headers=admin_headers,
            json={
                "observation_id": str(chain.observation_id),
                "decision": "CONFIRMED",
                "reviewed_at": future,
            },
        )
        assert response.status_code == 422

    async def test_rejected_history_not_physical(self, client, admin_headers, database):
        chain = await seed_observation_chain(database)
        response = await client.post(
            "/api/v1/reviews",
            headers=admin_headers,
            json={"observation_id": str(chain.observation_id), "decision": "REJECTED"},
        )
        assert response.status_code == 201, response.text
        async with database.session() as session:
            entries = (
                (
                    await session.execute(
                        select(AssetConditionHistory).where(
                            AssetConditionHistory.asset_id == chain.asset_id
                        )
                    )
                )
                .scalars()
                .all()
            )
        assert entries
        assert all(entry.is_physical_change is False for entry in entries)

    async def test_corrected_asset_type_bumps_version(self, client, admin_headers, database):
        chain = await seed_observation_chain(database)
        response = await client.post(
            "/api/v1/reviews",
            headers=admin_headers,
            json={
                "observation_id": str(chain.observation_id),
                "decision": "CORRECTED",
                "corrected_asset_type": "pole",
            },
        )
        assert response.status_code == 201, response.text
        asset = await client.get(f"/api/v1/assets/{chain.asset_id}", headers=admin_headers)
        assert asset.json()["asset_type"] == "pole"
        assert asset.json()["version"] == 2


class TestHistoryPagination:
    async def test_history_envelope_and_page_size(self, client, admin_headers, database):
        chain = await seed_observation_chain(database)
        async with database.session() as session:
            for index in range(3):
                session.add(
                    AssetConditionHistory(
                        asset_id=chain.asset_id,
                        change_source=ConditionChangeSource.MANUAL_EDIT,
                        new_condition="ok",
                        detected_at=datetime(2026, 11, 10 + index, 12, 0, tzinfo=UTC),
                    )
                )
            await session.commit()
        response = await client.get(
            f"/api/v1/assets/{chain.asset_id}/history",
            headers=admin_headers,
            params={"page_size": 2},
        )
        assert response.status_code == 200
        body = response.json()
        assert set(body) == {"items", "total", "page", "page_size", "pages"}
        assert body["total"] == 3
        assert body["pages"] == 2
        assert len(body["items"]) == 2
        assert body["items"][0]["detected_at"] >= body["items"][1]["detected_at"]


class TestSortAndDateValidation:
    @pytest.mark.parametrize(
        ("path", "sort_by"),
        [
            ("/api/v1/assets", "display_name"),
            ("/api/v1/jobs", "progress"),
            ("/api/v1/observations", "severity"),
            ("/api/v1/defects", "description"),
            ("/api/v1/reviews", "comment"),
            ("/api/v1/routes", "vehicle_id"),
        ],
    )
    async def test_unknown_sort_422(self, client, admin_headers, path, sort_by):
        response = await client.get(path, headers=admin_headers, params={"sort_by": sort_by})
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "validation_error"

    @pytest.mark.parametrize(
        ("path", "sort_by"),
        [
            ("/api/v1/assets", "current_priority"),
            ("/api/v1/jobs", "started_at"),
            ("/api/v1/observations", "detector_confidence"),
            ("/api/v1/defects", "severity"),
            ("/api/v1/reviews", "reviewed_at"),
            ("/api/v1/routes", "total_distance_m"),
        ],
    )
    async def test_whitelisted_sort_200(self, client, admin_headers, path, sort_by):
        response = await client.get(path, headers=admin_headers, params={"sort_by": sort_by})
        assert response.status_code == 200

    @pytest.mark.parametrize(
        "path",
        [
            "/api/v1/assets",
            "/api/v1/jobs",
            "/api/v1/observations",
            "/api/v1/defects",
            "/api/v1/reviews",
            "/api/v1/routes",
            "/api/v1/exports/assets",
            "/api/v1/map/observations",
        ],
    )
    async def test_inverted_date_range_422(self, client, admin_headers, path):
        response = await client.get(
            path,
            headers=admin_headers,
            params={"date_from": "2026-11-15T00:00:00Z", "date_to": "2026-11-14T00:00:00Z"},
        )
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "validation_error"

    async def test_map_invalid_priority_band_422(self, client, admin_headers):
        response = await client.get(
            "/api/v1/map/assets", headers=admin_headers, params={"priority_band": "BOGUS"}
        )
        assert response.status_code == 422

    async def test_map_valid_priority_band_200(self, client, admin_headers, database):
        await seed_asset(database, lon=37.6173, lat=55.7558)
        response = await client.get(
            "/api/v1/map/assets",
            headers=admin_headers,
            params={"priority_band": "HIGH_PRIORITY"},
        )
        assert response.status_code == 200


class TestExportsHardening:
    async def test_truncation_header(self, client, admin_headers, database, monkeypatch):
        await seed_asset(database)
        await seed_asset(database, asset_type="pole")
        monkeypatch.setattr("app.application.services.exports.EXPORT_ROW_LIMIT", 1)
        monkeypatch.setattr("app.api.v1.exports.EXPORT_ROW_LIMIT", 1)
        response = await client.get("/api/v1/exports/assets", headers=admin_headers)
        assert response.status_code == 200
        assert response.headers["X-Export-Truncated"] == "true"
        rows = list(csv.reader(io.StringIO(response.content.decode("utf-8-sig"))))
        assert len(rows) == 2

    async def test_no_truncation_header_below_limit(self, client, admin_headers, database):
        await seed_asset(database)
        response = await client.get("/api/v1/exports/assets", headers=admin_headers)
        assert response.status_code == 200
        assert "X-Export-Truncated" not in response.headers

    async def test_csv_formula_injection_escaped(self, client, admin_headers, database):
        await seed_asset(database, display_name="=1+1")
        response = await client.get("/api/v1/exports/assets", headers=admin_headers)
        assert response.status_code == 200
        rows = list(csv.reader(io.StringIO(response.content.decode("utf-8-sig"))))
        header = rows[0]
        assert rows[1][header.index("display_name")] == "'=1+1"

    async def test_observations_export_filter_parity(self, client, admin_headers, database):
        await seed_observation_chain(database)
        unreviewed = await client.get(
            "/api/v1/exports/observations",
            headers=admin_headers,
            params={"review_status": "UNREVIEWED"},
        )
        assert unreviewed.status_code == 200
        assert len(list(csv.reader(io.StringIO(unreviewed.content.decode("utf-8-sig"))))) == 2
        confirmed = await client.get(
            "/api/v1/exports/observations",
            headers=admin_headers,
            params={"review_status": "CONFIRMED"},
        )
        assert len(list(csv.reader(io.StringIO(confirmed.content.decode("utf-8-sig"))))) == 1
        dedup = await client.get(
            "/api/v1/exports/observations",
            headers=admin_headers,
            params={"dedup_result": "NEW_ASSET"},
        )
        assert len(list(csv.reader(io.StringIO(dedup.content.decode("utf-8-sig"))))) == 1


class TestSearchEscaping:
    async def test_routes_search_wildcards_literal(self, client, admin_headers, database):
        async with database.session() as session:
            session.add(Route(name="a%b", metadata_={}))
            session.add(Route(name="axb", metadata_={}))
            await session.commit()
        response = await client.get(
            "/api/v1/routes", headers=admin_headers, params={"search": "a%b"}
        )
        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 1
        assert body["items"][0]["name"] == "a%b"

    async def test_uploads_repo_search_wildcards_literal(self, database):
        async with database.session() as session:
            for name in ("a_b.jpg", "axb.jpg"):
                session.add(
                    Upload(
                        original_filename=name,
                        storage_key=f"uploads/{uuid.uuid4()}/{name}",
                        content_type="image/jpeg",
                        file_size=1,
                        checksum_sha256=hashlib.sha256(uuid.uuid4().bytes).hexdigest(),
                        media_type=MediaType.IMAGE,
                        metadata_={},
                    )
                )
            await session.commit()
        async with database.session() as session:
            stmt = UploadRepository(session).filtered_stmt(search="a_b")
            rows = (await session.execute(stmt)).scalars().all()
        assert [row.original_filename for row in rows] == ["a_b.jpg"]


class TestBatchQueryCounts:
    async def test_observations_page_bounded_selects(
        self, client, admin_headers, database, settings
    ):
        chain1 = await seed_observation_chain(database, lon=37.6173, lat=55.7558)
        chain2 = await seed_observation_chain(database)
        _write_physical_image(settings, chain1.image_storage_key)
        _write_physical_image(settings, chain2.image_storage_key)
        selects: list[str] = []

        def count_selects(conn, cursor, statement, parameters, context, executemany):
            if statement.lstrip().upper().startswith("SELECT"):
                selects.append(statement)

        event.listen(database.engine.sync_engine, "before_cursor_execute", count_selects)
        try:
            response = await client.get(
                "/api/v1/observations", headers=admin_headers, params={"page_size": 100}
            )
        finally:
            event.remove(database.engine.sync_engine, "before_cursor_execute", count_selects)
        assert response.status_code == 200
        items = response.json()["items"]
        assert len(items) == 2
        assert all(item["image_url"] for item in items)
        assert len(selects) <= 4, selects

    async def test_defects_page_bounded_selects(self, client, admin_headers, database):
        await seed_observation_chain(database, with_defect=True)
        await seed_observation_chain(database, with_defect=True)
        selects: list[str] = []

        def count_selects(conn, cursor, statement, parameters, context, executemany):
            if statement.lstrip().upper().startswith("SELECT"):
                selects.append(statement)

        event.listen(database.engine.sync_engine, "before_cursor_execute", count_selects)
        try:
            response = await client.get(
                "/api/v1/defects", headers=admin_headers, params={"page_size": 100}
            )
        finally:
            event.remove(database.engine.sync_engine, "before_cursor_execute", count_selects)
        assert response.status_code == 200
        items = response.json()["items"]
        assert len(items) == 2
        assert all(item["observation_count"] == 1 for item in items)
        assert len(selects) <= 4, selects


class TestMediaGating:
    async def test_viewer_gets_no_urls_admin_gets_urls(
        self, client, admin_headers, viewer_headers, database, settings
    ):
        chain = await seed_observation_chain(database)
        _write_physical_image(settings, chain.image_storage_key)
        admin_view = await client.get(
            f"/api/v1/observations/{chain.observation_id}", headers=admin_headers
        )
        assert admin_view.status_code == 200
        assert admin_view.json()["image_url"] is not None
        viewer_view = await client.get(
            f"/api/v1/observations/{chain.observation_id}", headers=viewer_headers
        )
        assert viewer_view.status_code == 200
        assert viewer_view.json()["image_url"] is None
        assert viewer_view.json()["crop_url"] is None


class TestRouteCreation:
    async def test_create_route_distance_audit_idempotency(self, client, admin_headers, database):
        body = {
            "name": "Survey run 1",
            "vehicle_id": "veh-1",
            "track": [[37.6173, 55.7558], [37.6200, 55.7560], [37.6230, 55.7565]],
        }
        headers = {**admin_headers, "Idempotency-Key": "route-key-1"}
        created = await client.post("/api/v1/routes", headers=headers, json=body)
        assert created.status_code == 201, created.text
        route = created.json()
        assert 300 < route["total_distance_m"] < 600
        assert route["track_geojson"]["type"] == "LineString"
        replay = await client.post("/api/v1/routes", headers=headers, json=body)
        assert replay.status_code == 201
        assert replay.json()["id"] == route["id"]
        conflict = await client.post(
            "/api/v1/routes", headers=headers, json={**body, "name": "Different"}
        )
        assert conflict.status_code == 409
        assert conflict.json()["error"]["code"] == "idempotency_conflict"
        async with database.session() as session:
            audits = (
                (
                    await session.execute(
                        select(AuditLog).where(
                            AuditLog.entity_type == "route",
                            AuditLog.action == AuditAction.CREATE.value,
                        )
                    )
                )
                .scalars()
                .all()
            )
        assert len(audits) == 1

    async def test_finished_before_started_422(self, client, admin_headers):
        response = await client.post(
            "/api/v1/routes",
            headers=admin_headers,
            json={
                "name": "bad",
                "started_at": "2026-11-15T12:00:00Z",
                "finished_at": "2026-11-15T11:00:00Z",
            },
        )
        assert response.status_code == 422


class TestAnalyticsAreaSemantics:
    async def test_route_stats_count_only_area_observations(self, client, admin_headers, database):
        inside = await seed_observation_chain(database, lon=37.6173, lat=55.7558)
        outside = await seed_observation_chain(database, lon=37.95, lat=55.95)
        route_id = uuid.uuid4()
        async with database.session() as session:
            session.add(Route(id=route_id, name="Area route", metadata_={}))
            await session.flush()
            for job_id in (inside.job_id, outside.job_id):
                await session.execute(
                    update(ProcessingJob)
                    .where(ProcessingJob.id == job_id)
                    .values(route_id=route_id)
                )
            await session.commit()
        response = await client.get("/api/v1/analytics/coverage", headers=admin_headers)
        assert response.status_code == 200
        routes = response.json()["routes"]
        entry = next(item for item in routes if item["route_id"] == str(route_id))
        assert entry["observations"] == 1
