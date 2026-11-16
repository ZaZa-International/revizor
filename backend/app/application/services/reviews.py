"""Human-in-the-loop review workflow.

Append-only reviews; original ML predictions are never overwritten.
Confirmed/corrected observations become training examples (controlled
active learning collection, no automatic retraining).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.services.history import AssetHistoryService
from app.application.services.risk import RiskScoringService
from app.core.exceptions import ValidationAppError
from app.domain.assets.taxonomy import is_known_asset_type
from app.domain.defects.taxonomy import is_known_defect_type
from app.domain.enums import (
    AuditAction,
    ConditionChangeSource,
    DefectStatus,
    ObservationReviewStatus,
    ReviewDecision,
)
from app.domain.observations.condition import is_valid_condition
from app.domain.reviews.logic import (
    EffectiveObservationState,
    ReviewCorrection,
    apply_review,
    validate_review,
)
from app.infrastructure.database.models.defect import Defect, defect_observations
from app.infrastructure.database.models.observation import Observation
from app.infrastructure.database.models.review import Review
from app.infrastructure.database.models.stored_file import StoredFile
from app.infrastructure.database.models.training import TrainingExample
from app.infrastructure.database.repositories.assets import AssetRepository
from app.infrastructure.database.repositories.defects import DefectRepository, ReviewRepository
from app.infrastructure.database.repositories.misc import TrainingExampleRepository
from app.infrastructure.database.repositories.observations import ObservationRepository
from app.infrastructure.database.repositories.users import AuditRepository

_DECISION_TO_STATUS = {
    ReviewDecision.CONFIRMED: ObservationReviewStatus.CONFIRMED,
    ReviewDecision.REJECTED: ObservationReviewStatus.REJECTED,
    ReviewDecision.CORRECTED: ObservationReviewStatus.CORRECTED,
    ReviewDecision.NEEDS_MORE_INFORMATION: ObservationReviewStatus.NEEDS_MORE_INFORMATION,
}

_REVIEWED_AT_MAX_SKEW = timedelta(minutes=5)


def validate_reviewed_at(reviewed_at: datetime | None) -> datetime | None:
    """Normalize naive timestamps to UTC and reject future dates beyond clock skew."""
    if reviewed_at is None:
        return None
    if reviewed_at.tzinfo is None:
        reviewed_at = reviewed_at.replace(tzinfo=UTC)
    if reviewed_at > datetime.now(UTC) + _REVIEWED_AT_MAX_SKEW:
        raise ValidationAppError("reviewed_at must not be more than 5 minutes in the future")
    return reviewed_at


class ReviewService:
    def __init__(
        self, session: AsyncSession, risk: RiskScoringService, history: AssetHistoryService
    ) -> None:
        self._session = session
        self._risk = risk
        self._history = history
        self._observations = ObservationRepository(session)
        self._defects = DefectRepository(session)
        self._reviews = ReviewRepository(session)
        self._assets = AssetRepository(session)
        self._training = TrainingExampleRepository(session)
        self._audit = AuditRepository(session)

    async def create_review(
        self,
        *,
        observation_id: uuid.UUID | None,
        defect_id: uuid.UUID | None,
        reviewer_id: uuid.UUID,
        decision: ReviewDecision,
        correction: ReviewCorrection,
        comment: str | None,
        reviewed_at: datetime | None = None,
    ) -> Review:
        if observation_id is None and defect_id is None:
            raise ValidationAppError("Review must target an observation or a defect")
        observation: Observation | None = None
        defect: Defect | None = None
        if observation_id is not None:
            observation = await self._observations.get_or_raise(observation_id)
        if defect_id is not None:
            defect = await self._defects.get_or_raise(defect_id)
        elif observation is not None:
            defect = await self._primary_defect(observation.id)

        try:
            validate_review(decision, correction, has_defect=defect is not None)
        except ValueError as exc:
            raise ValidationAppError(str(exc)) from exc
        if correction.corrected_asset_type is not None and not is_known_asset_type(
            correction.corrected_asset_type
        ):
            raise ValidationAppError(f"Unknown asset type {correction.corrected_asset_type!r}")
        if correction.corrected_defect_type is not None and not is_known_defect_type(
            correction.corrected_defect_type
        ):
            raise ValidationAppError(f"Unknown defect type {correction.corrected_defect_type!r}")
        if correction.corrected_condition is not None and not is_valid_condition(
            correction.corrected_condition
        ):
            raise ValidationAppError(f"Unknown condition {correction.corrected_condition!r}")
        reviewed_at = validate_reviewed_at(reviewed_at)

        review = Review(
            observation_id=observation_id,
            defect_id=defect.id if defect is not None else None,
            reviewer_id=reviewer_id,
            decision=decision,
            corrected_asset_type=correction.corrected_asset_type,
            corrected_condition=correction.corrected_condition,
            corrected_defect_type=correction.corrected_defect_type,
            corrected_severity=correction.corrected_severity,
            comment=comment,
            reviewed_at=reviewed_at or datetime.now(UTC),
        )
        self._reviews.add(review)
        await self._session.flush()

        if observation is not None:
            await self._apply_to_observation(observation, review, correction, defect)
        if defect is not None:
            await self._apply_to_defect(defect, review, correction, observation)

        self._audit.record(
            actor_id=reviewer_id,
            action=AuditAction.REVIEW.value,
            entity_type="review",
            entity_id=review.id,
            after_state={
                "decision": decision.value,
                "observation_id": str(observation_id) if observation_id else None,
                "defect_id": str(defect.id) if defect else None,
            },
        )
        await self._session.flush()
        return review

    async def _primary_defect(self, observation_id: uuid.UUID) -> Defect | None:
        stmt = (
            select(Defect)
            .join(defect_observations, defect_observations.c.defect_id == Defect.id)
            .where(defect_observations.c.observation_id == observation_id)
            .limit(1)
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def _apply_to_observation(
        self,
        observation: Observation,
        review: Review,
        correction: ReviewCorrection,
        defect: Defect | None,
    ) -> None:
        effective = apply_review(
            original_asset_type=observation.object_type,
            original_condition=observation.condition_class or "unknown",
            original_severity=observation.severity,
            original_defect_type=defect.defect_type if defect else None,
            decision=review.decision,
            correction=correction,
        )
        observation.review_status = _DECISION_TO_STATUS[review.decision]
        observation.effective_asset_type = effective.asset_type
        observation.effective_condition = effective.condition
        observation.effective_severity = effective.severity

        if review.decision in (ReviewDecision.CONFIRMED, ReviewDecision.CORRECTED):
            await self._upsert_training_example(observation, review, effective)

        if observation.asset_id is not None:
            asset = await self._assets.get_or_raise(observation.asset_id)
            asset_type_changed = False
            if (
                review.decision == ReviewDecision.CORRECTED
                and correction.corrected_asset_type
                and correction.corrected_asset_type != asset.asset_type
            ):
                asset.asset_type = correction.corrected_asset_type
                asset_type_changed = True
            assessment = self._risk.assess(
                asset_type=effective.asset_type,
                severity=effective.severity,
                confidence=observation.detector_confidence,
                review_decision=review.decision,
                deduplication_result=observation.dedup_result,
                manual_override=asset.priority_override,
            )
            history_entry = await self._history.record_change(
                asset=asset,
                new_condition=effective.condition,
                new_severity=effective.severity,
                new_priority=assessment.priority,
                source=ConditionChangeSource.HUMAN_REVIEW,
                detected_at=review.reviewed_at,
                observation_id=observation.id,
                review_id=review.id,
                review_decision=review.decision,
            )
            if not effective.is_rejected:
                asset.current_condition = effective.condition
                asset.current_severity = effective.severity
            self._risk.apply_to_asset(asset, assessment)
            if asset_type_changed or history_entry is not None:
                asset.version += 1

    async def _upsert_training_example(
        self, observation: Observation, review: Review, effective: object
    ) -> None:
        assert isinstance(effective, EffectiveObservationState)
        image_key = None
        if observation.image_id is not None:
            stored = await self._session.get(StoredFile, observation.image_id)
            image_key = stored.storage_key if stored else None
        if image_key is None:
            return
        label = {
            "object_type": effective.asset_type,
            "condition": effective.condition,
            "severity": effective.severity,
            "defect_type": effective.defect_type,
            "bbox": observation.bbox,
            "image_width": observation.image_width,
            "image_height": observation.image_height,
            "review_decision": review.decision.value,
        }
        stmt = (
            pg_insert(TrainingExample)
            .values(
                observation_id=observation.id,
                review_id=review.id,
                image_storage_key=image_key,
                label=label,
            )
            .on_conflict_do_update(
                index_elements=["observation_id"],
                set_={"review_id": review.id, "label": label, "image_storage_key": image_key},
            )
        )
        await self._session.execute(stmt)

    async def _apply_to_defect(
        self,
        defect: Defect,
        review: Review,
        correction: ReviewCorrection,
        observation: Observation | None,
    ) -> None:
        if review.decision == ReviewDecision.REJECTED:
            if observation is not None:
                count = await self._defects.observation_count(defect.id)
                if count > 1:
                    return
            defect.status = DefectStatus.REJECTED
        elif review.decision == ReviewDecision.CONFIRMED:
            if defect.status == DefectStatus.OPEN:
                defect.status = DefectStatus.CONFIRMED
        elif review.decision == ReviewDecision.CORRECTED:
            if correction.corrected_defect_type:
                defect.defect_type = correction.corrected_defect_type
            if correction.corrected_severity is not None:
                defect.severity = correction.corrected_severity
            if defect.status == DefectStatus.OPEN:
                defect.status = DefectStatus.CONFIRMED
