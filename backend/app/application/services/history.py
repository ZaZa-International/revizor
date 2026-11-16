"""Asset condition history and change detection.

A change of ML class between observations is NOT automatically a physical
change: is_physical_change is True only for human-confirmed sources or when
both sides of the transition are human-verified.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import ConditionChangeSource, ObservationReviewStatus, ReviewDecision
from app.infrastructure.database.models.asset import Asset
from app.infrastructure.database.models.history import AssetConditionHistory
from app.infrastructure.database.models.observation import Observation
from app.infrastructure.database.repositories.misc import HistoryRepository

_HUMAN_VERIFIED = {ObservationReviewStatus.CONFIRMED, ObservationReviewStatus.CORRECTED}


class AssetHistoryService:
    def __init__(self, session: AsyncSession) -> None:
        self._history = HistoryRepository(session)

    async def list_for_asset(self, asset_id: uuid.UUID) -> list[AssetConditionHistory]:
        return await self._history.list_for_asset(asset_id)

    async def record_change(
        self,
        *,
        asset: Asset,
        new_condition: str | None,
        new_severity: int | None,
        new_priority: float | None,
        source: ConditionChangeSource,
        detected_at: datetime,
        observation_id: uuid.UUID | None = None,
        review_id: uuid.UUID | None = None,
        observation_review_status: ObservationReviewStatus | None = None,
        review_decision: ReviewDecision | None = None,
        note: str | None = None,
    ) -> AssetConditionHistory | None:
        changed = (
            asset.current_condition != new_condition
            or asset.current_severity != new_severity
            or (
                new_priority is not None
                and (
                    asset.current_priority is None
                    or abs(asset.current_priority - new_priority) > 0.01
                )
            )
        )
        if not changed:
            return None
        if source == ConditionChangeSource.ML_PREDICTION:
            is_physical = observation_review_status in _HUMAN_VERIFIED
            if not is_physical and note is None:
                note = "ml_prediction_change_not_confirmed_as_physical"
        else:
            is_physical = review_decision != ReviewDecision.REJECTED
            if not is_physical and note is None:
                note = "rejected_prediction_not_a_physical_change"
        entry = AssetConditionHistory(
            asset_id=asset.id,
            observation_id=observation_id,
            review_id=review_id,
            change_source=source,
            previous_condition=asset.current_condition,
            new_condition=new_condition,
            previous_severity=asset.current_severity,
            new_severity=new_severity,
            previous_priority=asset.current_priority,
            new_priority=new_priority,
            is_physical_change=is_physical,
            note=note,
            detected_at=detected_at,
        )
        return self._history.add(entry)

    async def record_observation(
        self,
        *,
        asset: Asset,
        observation: Observation,
        new_priority: float | None,
    ) -> AssetConditionHistory | None:
        return await self.record_change(
            asset=asset,
            new_condition=observation.effective_condition or observation.condition_class,
            new_severity=(
                observation.effective_severity
                if observation.effective_severity is not None
                else observation.severity
            ),
            new_priority=new_priority,
            source=ConditionChangeSource.ML_PREDICTION,
            detected_at=observation.observed_at,
            observation_id=observation.id,
            observation_review_status=observation.review_status,
        )
