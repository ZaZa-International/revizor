import pytest
from app.domain.enums import ReviewDecision
from app.domain.reviews.logic import ReviewCorrection, apply_review, validate_review

pytestmark = pytest.mark.unit


def test_corrected_requires_at_least_one_correction():
    with pytest.raises(ValueError):
        validate_review(ReviewDecision.CORRECTED, ReviewCorrection(), has_defect=False)


def test_corrections_only_with_corrected_decision():
    with pytest.raises(ValueError):
        validate_review(
            ReviewDecision.CONFIRMED,
            ReviewCorrection(corrected_severity=3),
            has_defect=False,
        )


def test_severity_range_validated():
    with pytest.raises(ValueError):
        validate_review(
            ReviewDecision.CORRECTED, ReviewCorrection(corrected_severity=9), has_defect=False
        )


def test_confirmed_preserves_original():
    state = apply_review(
        original_asset_type="telecom_well",
        original_condition="damaged_cover",
        original_severity=4,
        original_defect_type="damaged_cover",
        decision=ReviewDecision.CONFIRMED,
        correction=None,
    )
    assert state.asset_type == "telecom_well"
    assert state.condition == "damaged_cover"
    assert state.severity == 4
    assert not state.is_rejected


def test_corrected_overrides_only_provided_fields():
    state = apply_review(
        original_asset_type="telecom_well",
        original_condition="damaged_cover",
        original_severity=4,
        original_defect_type="damaged_cover",
        decision=ReviewDecision.CORRECTED,
        correction=ReviewCorrection(corrected_severity=2, corrected_condition="ok"),
    )
    assert state.severity == 2
    assert state.condition == "ok"
    assert state.asset_type == "telecom_well"


def test_rejected_marks_rejected_but_keeps_original_values():
    state = apply_review(
        original_asset_type="pole",
        original_condition="tilted",
        original_severity=4,
        original_defect_type="pole_tilt",
        decision=ReviewDecision.REJECTED,
        correction=None,
    )
    assert state.is_rejected
    assert state.condition == "tilted"
    assert state.severity == 4


def test_no_review_normalizes_condition():
    state = apply_review(
        original_asset_type="pole",
        original_condition="leaning",
        original_severity=None,
        original_defect_type=None,
        decision=None,
        correction=None,
    )
    assert state.condition == "tilted"
    assert state.review_decision is None


def test_needs_more_information_keeps_state():
    state = apply_review(
        original_asset_type="pole",
        original_condition="tilted",
        original_severity=4,
        original_defect_type="pole_tilt",
        decision=ReviewDecision.NEEDS_MORE_INFORMATION,
        correction=None,
    )
    assert not state.is_rejected
    assert state.review_decision == ReviewDecision.NEEDS_MORE_INFORMATION
