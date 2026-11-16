"""Wave-1 API semantics: patch presence, vocabularies, transitions, escaping,
idempotency fingerprints, pagination helpers, sort/date validation (pure unit)."""

from __future__ import annotations

import csv
import io
import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from app.api.v1.exports import _attachment
from app.api.v1.idempotency import idempotent_post
from app.api.v1.params import (
    AssetSort,
    DefectSort,
    JobSort,
    ObservationSort,
    ReviewSort,
    RouteSort,
    validate_date_range,
)
from app.application.services.exports import ExportService
from app.application.services.reviews import validate_reviewed_at
from app.core.exceptions import IdempotencyConflictError, ValidationAppError
from app.domain.defects.transitions import (
    InvalidDefectTransitionError,
    assert_defect_transition,
    can_transition_defect,
)
from app.domain.enums import DefectStatus
from app.domain.observations.condition import is_valid_condition
from app.infrastructure.database.models.idempotency import IdempotencyRecord
from app.infrastructure.database.repositories.base import Page, like_contains
from app.schemas.analytics import KeyValueCount
from app.schemas.assets import AssetPatchRequest, DefectPatchRequest
from app.schemas.common import page_dict, page_response
from app.schemas.routes import RouteCreateRequest
from pydantic import TypeAdapter, ValidationError

pytestmark = pytest.mark.unit


class TestAssetPatchPresence:
    def test_reason_only_allowed(self):
        body = AssetPatchRequest(priority_override_reason="storm damage")
        assert body.model_dump(exclude_unset=True) == {"priority_override_reason": "storm damage"}

    def test_override_clear_only_allowed(self):
        body = AssetPatchRequest(priority_override=None)
        assert body.model_dump(exclude_unset=True) == {"priority_override": None}

    def test_explicit_null_display_name_allowed(self):
        body = AssetPatchRequest(display_name=None)
        assert body.model_dump(exclude_unset=True) == {"display_name": None}

    def test_empty_patch_rejected(self):
        with pytest.raises(ValidationError):
            AssetPatchRequest()

    def test_expected_version_only_rejected(self):
        with pytest.raises(ValidationError):
            AssetPatchRequest(expected_version=3)

    def test_reason_max_length(self):
        AssetPatchRequest(priority_override_reason="x" * 2000)
        with pytest.raises(ValidationError):
            AssetPatchRequest(priority_override_reason="x" * 2001)


class TestDefectPatchPresence:
    def test_explicit_null_description_allowed(self):
        body = DefectPatchRequest(description=None)
        assert body.model_dump(exclude_unset=True) == {"description": None}

    def test_empty_patch_rejected(self):
        with pytest.raises(ValidationError):
            DefectPatchRequest()


class TestConditionVocabulary:
    @pytest.mark.parametrize(
        "label",
        [
            "ok",
            "damaged",
            "damaged_cover",
            "missing_cover",
            "door_open",
            "tilted",
            "unknown",
            "broken",
            "Open Door",
            "cable-sag",
        ],
    )
    def test_valid(self, label):
        assert is_valid_condition(label)

    @pytest.mark.parametrize("label", ["totally_bogus", "", "ok-ish", "sev5"])
    def test_invalid(self, label):
        assert not is_valid_condition(label)


class TestReviewedAtBound:
    def test_none_passthrough(self):
        assert validate_reviewed_at(None) is None

    def test_naive_normalized_to_utc(self):
        result = validate_reviewed_at(datetime(2026, 11, 15, 12, 0))
        assert result is not None and result.tzinfo == UTC

    def test_within_skew_allowed(self):
        validate_reviewed_at(datetime.now(UTC) + timedelta(minutes=4))

    def test_future_beyond_skew_rejected(self):
        with pytest.raises(ValidationAppError):
            validate_reviewed_at(datetime.now(UTC) + timedelta(minutes=6))

    def test_naive_future_rejected(self):
        future = (datetime.now(UTC) + timedelta(hours=1)).replace(tzinfo=None)
        with pytest.raises(ValidationAppError):
            validate_reviewed_at(future)


_ALLOWED_TRANSITIONS = {
    DefectStatus.OPEN: {
        DefectStatus.CONFIRMED,
        DefectStatus.IN_PROGRESS,
        DefectStatus.RESOLVED,
        DefectStatus.REJECTED,
    },
    DefectStatus.CONFIRMED: {DefectStatus.IN_PROGRESS, DefectStatus.RESOLVED},
    DefectStatus.IN_PROGRESS: {DefectStatus.CONFIRMED, DefectStatus.RESOLVED},
    DefectStatus.RESOLVED: {DefectStatus.OPEN},
    DefectStatus.REJECTED: set(),
}


class TestDefectTransitionMatrix:
    @pytest.mark.parametrize("current", list(DefectStatus))
    @pytest.mark.parametrize("target", list(DefectStatus))
    def test_matrix(self, current, target):
        allowed = target == current or target in _ALLOWED_TRANSITIONS[current]
        assert can_transition_defect(current, target) == (target in _ALLOWED_TRANSITIONS[current])
        if allowed:
            assert_defect_transition(current, target)
        else:
            with pytest.raises(InvalidDefectTransitionError):
                assert_defect_transition(current, target)

    def test_rejected_is_terminal(self):
        for target in DefectStatus:
            if target != DefectStatus.REJECTED:
                with pytest.raises(InvalidDefectTransitionError):
                    assert_defect_transition(DefectStatus.REJECTED, target)


class TestCsvFormulaEscaping:
    def _render(self, rows):
        service = ExportService(MagicMock())
        content, _, _ = service.render(
            rows, ["name", "value"], "csv", entity="assets", actor_id=None
        )
        return list(csv.reader(io.StringIO(content.decode("utf-8-sig"))))

    @pytest.mark.parametrize("payload", ["=1+1", "+cmd", "-2+3", "@SUM(A1)", "\tcmd", "\rcmd"])
    def test_dangerous_prefix_escaped(self, payload):
        rows = self._render([{"name": payload, "value": 1}])
        assert rows[1][0] == "'" + payload

    def test_safe_cells_untouched(self):
        rows = self._render([{"name": "well-42", "value": -5}])
        assert rows[1] == ["well-42", "-5"]


class TestDateRangeValidator:
    def test_inverted_rejected(self):
        with pytest.raises(ValidationAppError):
            validate_date_range(
                datetime(2026, 11, 15, tzinfo=UTC), datetime(2026, 11, 14, tzinfo=UTC)
            )

    def test_equal_allowed(self):
        moment = datetime(2026, 11, 15, tzinfo=UTC)
        validate_date_range(moment, moment)

    def test_open_bounds_allowed(self):
        validate_date_range(None, datetime(2026, 11, 15, tzinfo=UTC))
        validate_date_range(datetime(2026, 11, 15, tzinfo=UTC), None)
        validate_date_range(None, None)

    def test_mixed_naive_aware_comparable(self):
        validate_date_range(datetime(2026, 11, 14), datetime(2026, 11, 15, tzinfo=UTC))
        with pytest.raises(ValidationAppError):
            validate_date_range(datetime(2026, 11, 16), datetime(2026, 11, 15, tzinfo=UTC))


class TestSortEnums:
    @pytest.mark.parametrize(
        ("alias", "valid"),
        [
            (AssetSort, "current_priority"),
            (JobSort, "started_at"),
            (ObservationSort, "detector_confidence"),
            (DefectSort, "severity"),
            (ReviewSort, "reviewed_at"),
            (RouteSort, "total_distance_m"),
        ],
    )
    def test_unknown_rejected(self, alias, valid):
        adapter = TypeAdapter(alias | None)
        assert adapter.validate_python(valid) == valid
        assert adapter.validate_python(None) is None
        with pytest.raises(ValidationError):
            adapter.validate_python("bogus_field")

    def test_asset_whitelist_exact(self):
        adapter = TypeAdapter(AssetSort)
        for value in (
            "created_at",
            "last_observed_at",
            "current_priority",
            "current_severity",
            "asset_type",
        ):
            adapter.validate_python(value)
        with pytest.raises(ValidationError):
            adapter.validate_python("display_name")


def _cached_record(request_hash: str | None) -> IdempotencyRecord:
    return IdempotencyRecord(
        key="k",
        user_id=uuid.uuid4(),
        endpoint="POST /reviews",
        request_hash=request_hash,
        response_status=201,
        response_body={"id": "cached"},
    )


def _session_with_cached(record: IdempotencyRecord | None) -> AsyncMock:
    session = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = record
    session.execute.return_value = result

    @asynccontextmanager
    async def _nested():
        yield

    session.begin_nested = MagicMock(side_effect=lambda: _nested())
    session.add = MagicMock()
    return session


class TestIdempotencyFingerprint:
    async def test_mismatch_raises_conflict(self):
        session = _session_with_cached(_cached_record("a" * 64))
        handler = AsyncMock()
        with pytest.raises(IdempotencyConflictError):
            await idempotent_post(
                session,
                user_id=uuid.uuid4(),
                endpoint="POST /reviews",
                key="k",
                handler=handler,
                request_hash="b" * 64,
            )
        handler.assert_not_awaited()

    async def test_matching_hash_replays_cached_body(self):
        session = _session_with_cached(_cached_record("a" * 64))
        handler = AsyncMock()
        response = await idempotent_post(
            session,
            user_id=uuid.uuid4(),
            endpoint="POST /reviews",
            key="k",
            handler=handler,
            request_hash="a" * 64,
        )
        assert response.status_code == 201
        assert b"cached" in response.body
        handler.assert_not_awaited()

    async def test_legacy_record_without_hash_replays(self):
        session = _session_with_cached(_cached_record(None))
        response = await idempotent_post(
            session,
            user_id=uuid.uuid4(),
            endpoint="POST /reviews",
            key="k",
            handler=AsyncMock(),
            request_hash="b" * 64,
        )
        assert response.status_code == 201

    async def test_save_stores_request_hash(self):
        session = _session_with_cached(None)
        user_id = uuid.uuid4()
        response = await idempotent_post(
            session,
            user_id=user_id,
            endpoint="POST /reviews",
            key="k",
            handler=AsyncMock(return_value=(201, {"id": "new"})),
            request_hash="c" * 64,
        )
        assert response.status_code == 201
        saved = session.add.call_args[0][0]
        assert saved.request_hash == "c" * 64

    async def test_result_hash_fallback(self):
        session = _session_with_cached(None)
        await idempotent_post(
            session,
            user_id=uuid.uuid4(),
            endpoint="POST /uploads",
            key="k",
            handler=AsyncMock(return_value=(201, {"checksum": "abc"})),
            result_hash=lambda body: body.get("checksum"),
        )
        saved = session.add.call_args[0][0]
        assert saved.request_hash == "abc"

    async def test_no_key_skips_cache(self):
        session = _session_with_cached(_cached_record("a" * 64))
        handler = AsyncMock(return_value=(201, {"id": "fresh"}))
        response = await idempotent_post(
            session,
            user_id=uuid.uuid4(),
            endpoint="POST /reviews",
            key=None,
            handler=handler,
            request_hash="b" * 64,
        )
        assert response.status_code == 201
        handler.assert_awaited_once()
        session.add.assert_not_called()


class TestPaginationHelpers:
    def test_page_dict_envelope(self):
        page = Page(items=[{"a": 1}], total=3, page=1, page_size=2)
        body = page_dict([{"a": 1}], page)
        assert body == {"items": [{"a": 1}], "total": 3, "page": 1, "page_size": 2, "pages": 2}

    def test_page_response_serializes_items(self):
        page = Page(items=[KeyValueCount(key="pole", count=2)], total=1, page=1, page_size=20)
        body = page_response(page, KeyValueCount)
        assert body["items"] == [{"key": "pole", "count": 2}]
        assert body["pages"] == 1


class TestExportTruncationHeader:
    def test_truncated_header_present(self):
        response = _attachment(b"x", "text/csv", "assets.csv", truncated=True)
        assert response.headers["X-Export-Truncated"] == "true"

    def test_not_truncated_header_absent(self):
        response = _attachment(b"x", "text/csv", "assets.csv")
        assert "X-Export-Truncated" not in response.headers


class TestRouteCreateValidation:
    def test_track_max_points(self):
        RouteCreateRequest(name="r", track=[[37.6, 55.7], [37.61, 55.71]])
        with pytest.raises(ValidationError):
            RouteCreateRequest(name="r", track=[[37.6, 55.7]] * 10001)

    def test_finished_before_started_rejected(self):
        with pytest.raises(ValidationError):
            RouteCreateRequest(
                name="r",
                started_at=datetime(2026, 11, 15, 12, 0, tzinfo=UTC),
                finished_at=datetime(2026, 11, 15, 11, 0, tzinfo=UTC),
            )

    def test_equal_times_allowed(self):
        moment = datetime(2026, 11, 15, 12, 0, tzinfo=UTC)
        RouteCreateRequest(name="r", started_at=moment, finished_at=moment)


class TestLikeEscaping:
    def test_wildcards_escaped(self):
        assert like_contains("a%b_c\\d") == "%a\\%b\\_c\\\\d%"

    def test_plain_substring(self):
        assert like_contains("well") == "%well%"


class TestJobOptionsContract:
    def test_options_description(self):
        from app.schemas.uploads import JobCreateRequest

        description = JobCreateRequest.model_fields["options"].description
        assert description and "informational" in description
