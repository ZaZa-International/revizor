"""Risk scoring application service: wraps the versioned domain policy."""

from __future__ import annotations

from app.config import Settings
from app.domain.enums import DeduplicationResult, ReviewDecision
from app.domain.risk.scoring import RiskAssessment, RiskInput, RiskPolicy, assess_risk
from app.infrastructure.database.models.asset import Asset


class RiskScoringService:
    def __init__(self, settings: Settings) -> None:
        self._policy = RiskPolicy(
            version=settings.risk_policy_version,
            high_threshold=settings.risk_high_threshold,
            medium_threshold=settings.risk_medium_threshold,
            review_confidence_threshold=settings.risk_review_confidence_threshold,
        )

    @property
    def policy(self) -> RiskPolicy:
        return self._policy

    def assess(
        self,
        *,
        asset_type: str,
        severity: int | None,
        confidence: float,
        review_decision: ReviewDecision | None = None,
        deduplication_result: DeduplicationResult | None = None,
        manual_override: float | None = None,
    ) -> RiskAssessment:
        return assess_risk(
            RiskInput(
                asset_type=asset_type,
                severity=severity,
                confidence=confidence,
                review_decision=review_decision,
                deduplication_result=deduplication_result,
                manual_override=manual_override,
            ),
            self._policy,
        )

    def apply_to_asset(self, asset: Asset, assessment: RiskAssessment) -> None:
        asset.current_priority = assessment.priority
        asset.priority_band = assessment.band
        asset.priority_factors = assessment.factors
        asset.priority_policy_version = assessment.policy_version
