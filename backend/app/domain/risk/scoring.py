"""Transparent, configurable risk scoring policy (versioned).

priority = 100 * severity_normalized * impact_factor * confidence_factor

This is a project heuristic, NOT an industry standard. Low confidence never
proves absence of a problem: it reduces the score moderately and can route
the asset to NEEDS_REVIEW instead of silently lowering priority.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.domain.assets.taxonomy import get_asset_type
from app.domain.enums import DeduplicationResult, PriorityBand, ReviewDecision

UNKNOWN_SEVERITY_NORM = 0.5


@dataclass(frozen=True)
class RiskPolicy:
    version: str = "1.0"
    high_threshold: float = 70.0
    medium_threshold: float = 40.0
    review_confidence_threshold: float = 0.6


@dataclass(frozen=True)
class RiskInput:
    asset_type: str
    severity: int | None
    confidence: float
    review_decision: ReviewDecision | None = None
    deduplication_result: DeduplicationResult | None = None
    manual_override: float | None = None


@dataclass(frozen=True)
class RiskAssessment:
    priority: float
    band: PriorityBand
    policy_version: str
    factors: dict[str, object]


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def assess_risk(data: RiskInput, policy: RiskPolicy) -> RiskAssessment:
    if not 0.0 <= data.confidence <= 1.0:
        raise ValueError("confidence must be within [0, 1]")
    if data.severity is not None and not 1 <= data.severity <= 5:
        raise ValueError("severity must be within [1, 5]")

    asset_def = get_asset_type(data.asset_type)
    impact_factor = asset_def.impact_factor if asset_def else 0.5
    severity_known = data.severity is not None
    severity_norm = (
        (data.severity - 1) / 4.0 if data.severity is not None else UNKNOWN_SEVERITY_NORM
    )
    confidence_factor = 0.5 + 0.5 * data.confidence

    computed = _clamp(100.0 * severity_norm * impact_factor * confidence_factor)
    overridden = data.manual_override is not None
    priority = _clamp(data.manual_override) if data.manual_override is not None else computed

    needs_review = (
        data.review_decision is None
        and (
            data.confidence < policy.review_confidence_threshold
            or not severity_known
            or data.deduplication_result
            in (DeduplicationResult.POSSIBLE_MATCH, DeduplicationResult.AMBIGUOUS)
        )
    ) or data.review_decision == ReviewDecision.NEEDS_MORE_INFORMATION

    if data.review_decision == ReviewDecision.REJECTED:
        band = PriorityBand.LOW_PRIORITY
        priority = 0.0
    elif needs_review and not overridden:
        band = PriorityBand.NEEDS_REVIEW
    elif priority >= policy.high_threshold:
        band = PriorityBand.HIGH_PRIORITY
    elif priority >= policy.medium_threshold:
        band = PriorityBand.MEDIUM_PRIORITY
    else:
        band = PriorityBand.LOW_PRIORITY

    factors: dict[str, object] = {
        "severity": data.severity,
        "severity_normalized": round(severity_norm, 4),
        "severity_known": severity_known,
        "impact_factor": impact_factor,
        "confidence": data.confidence,
        "confidence_factor": round(confidence_factor, 4),
        "computed_priority": round(computed, 2),
        "manual_override": data.manual_override,
        "review_decision": data.review_decision.value if data.review_decision else None,
        "deduplication_result": (
            data.deduplication_result.value if data.deduplication_result else None
        ),
    }
    return RiskAssessment(round(priority, 2), band, policy.version, factors)
