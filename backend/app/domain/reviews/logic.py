"""Pure review decision logic.

Reviews are append-only: a new review never mutates previous reviews.
The latest review determines the effective review state of an observation;
original ML predictions are preserved untouched.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.domain.enums import ReviewDecision
from app.domain.observations.condition import normalize_condition


@dataclass(frozen=True)
class ReviewCorrection:
    corrected_asset_type: str | None = None
    corrected_condition: str | None = None
    corrected_defect_type: str | None = None
    corrected_severity: int | None = None


@dataclass(frozen=True)
class EffectiveObservationState:
    """Observation state after applying the latest human review (if any)."""

    asset_type: str
    condition: str
    severity: int | None
    defect_type: str | None
    is_rejected: bool
    review_decision: ReviewDecision | None


def validate_review(
    decision: ReviewDecision, correction: ReviewCorrection, *, has_defect: bool
) -> None:
    if decision == ReviewDecision.CORRECTED and not any(
        (
            correction.corrected_asset_type,
            correction.corrected_condition,
            correction.corrected_defect_type,
            correction.corrected_severity is not None,
        )
    ):
        raise ValueError("CORRECTED review must contain at least one correction")
    if decision != ReviewDecision.CORRECTED and any(
        (
            correction.corrected_asset_type,
            correction.corrected_condition,
            correction.corrected_defect_type,
            correction.corrected_severity is not None,
        )
    ):
        raise ValueError("Corrections are only allowed with CORRECTED decision")
    if correction.corrected_severity is not None and not 1 <= correction.corrected_severity <= 5:
        raise ValueError("corrected_severity must be within [1, 5]")
    if correction.corrected_defect_type and not has_defect and decision != ReviewDecision.CORRECTED:
        raise ValueError("defect correction requires a linked defect")


def apply_review(
    *,
    original_asset_type: str,
    original_condition: str,
    original_severity: int | None,
    original_defect_type: str | None,
    decision: ReviewDecision | None,
    correction: ReviewCorrection | None,
) -> EffectiveObservationState:
    if decision is None or decision == ReviewDecision.NEEDS_MORE_INFORMATION:
        return EffectiveObservationState(
            original_asset_type,
            normalize_condition(original_condition),
            original_severity,
            original_defect_type,
            False,
            decision,
        )
    if decision == ReviewDecision.REJECTED:
        return EffectiveObservationState(
            original_asset_type,
            normalize_condition(original_condition),
            original_severity,
            original_defect_type,
            True,
            decision,
        )
    if decision == ReviewDecision.CONFIRMED:
        return EffectiveObservationState(
            original_asset_type,
            normalize_condition(original_condition),
            original_severity,
            original_defect_type,
            False,
            decision,
        )
    assert correction is not None
    return EffectiveObservationState(
        correction.corrected_asset_type or original_asset_type,
        normalize_condition(correction.corrected_condition or original_condition),
        (
            correction.corrected_severity
            if correction.corrected_severity is not None
            else original_severity
        ),
        correction.corrected_defect_type or original_defect_type,
        False,
        decision,
    )
