"""Application-level deduplication: PostGIS candidates + domain policy.

Never merges ambiguous candidates automatically; every decision carries a
machine-readable explanation persisted on the observation.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.interfaces.embeddings import EmbeddingSimilarityProvider
from app.config import Settings
from app.core import metrics
from app.domain.assets.taxonomy import get_asset_type
from app.domain.deduplication.policy import (
    CandidateEvidence,
    DeduplicationConfig,
    DeduplicationDecision,
    decide,
)
from app.domain.enums import DeduplicationResult
from app.domain.geospatial.models import GeoPoint
from app.infrastructure.database.models.observation import Observation
from app.infrastructure.database.repositories.assets import AssetRepository
from app.infrastructure.database.repositories.observations import ObservationRepository


class DeduplicationService:
    def __init__(
        self,
        session: AsyncSession,
        settings: Settings,
        embeddings: EmbeddingSimilarityProvider | None = None,
    ) -> None:
        self._session = session
        self._assets = AssetRepository(session)
        self._observations = ObservationRepository(session)
        self._embeddings = embeddings
        self._max_candidates = settings.dedup_max_candidates
        self._config = DeduplicationConfig(
            radius_m=settings.dedup_radius_m,
            match_threshold=settings.dedup_match_threshold,
            possible_threshold=settings.dedup_possible_threshold,
            time_window_hours=settings.dedup_time_window_hours,
        )

    async def match(
        self,
        *,
        object_type: str,
        point: GeoPoint | None,
        observed_at: datetime,
        job_id: uuid.UUID,
        route_id: uuid.UUID | None,
        tracking_id: str | None,
        embedding: list[float] | None = None,
    ) -> DeduplicationDecision:
        if point is None:
            decision = await self._match_by_tracking(
                object_type=object_type, job_id=job_id, tracking_id=tracking_id
            )
            metrics.DEDUP_RESULTS.labels(decision.result.value).inc()
            return decision

        asset_def = get_asset_type(object_type)
        radius = asset_def.dedup_radius_m if asset_def else self._config.radius_m
        config = DeduplicationConfig(
            radius_m=radius,
            match_threshold=self._config.match_threshold,
            possible_threshold=self._config.possible_threshold,
            time_window_hours=self._config.time_window_hours,
        )
        candidates = await self._assets.find_candidates(
            point=point, radius_m=radius, asset_type=object_type, limit=self._max_candidates
        )
        evidence: list[CandidateEvidence] = []
        if candidates:
            candidate_ids = [asset.id for asset, _ in candidates]
            latest = await self._observations.batch_latest_for_assets(candidate_ids)
            on_route = (
                await self._observations.assets_on_route(candidate_ids, route_id)
                if route_id is not None
                else set()
            )
            with_tracking = (
                await self._observations.assets_with_tracking(candidate_ids, job_id, tracking_id)
                if tracking_id is not None
                else set()
            )
            for asset, distance_m in candidates:
                latest_row = latest.get(asset.id)
                last_observed = latest_row[0] if latest_row is not None else asset.last_observed_at
                hours = None
                if last_observed is not None:
                    hours = max(0.0, (observed_at - last_observed).total_seconds() / 3600.0)
                evidence.append(
                    CandidateEvidence(
                        asset_id=str(asset.id),
                        asset_type=asset.asset_type,
                        distance_m=distance_m,
                        hours_since_last_observation=hours,
                        same_route=asset.id in on_route,
                        same_tracking_id=asset.id in with_tracking,
                        visual_similarity=None,
                        embedding_similarity=None,
                    )
                )
        decision = decide(evidence, object_type=object_type, config=config)
        metrics.DEDUP_RESULTS.labels(decision.result.value).inc()
        return decision

    async def _match_by_tracking(
        self, *, object_type: str, job_id: uuid.UUID, tracking_id: str | None
    ) -> DeduplicationDecision:
        if tracking_id is None:
            return DeduplicationDecision(
                DeduplicationResult.NEW_ASSET,
                None,
                0.0,
                {"reason": "no_geolocation_and_no_tracking_id"},
            )
        stmt = (
            select(Observation)
            .where(
                Observation.processing_job_id == job_id,
                Observation.tracking_id == tracking_id,
                Observation.object_type == object_type,
                Observation.asset_id.is_not(None),
            )
            .order_by(Observation.observed_at.asc())
            .limit(1)
        )
        previous = (await self._session.execute(stmt)).scalar_one_or_none()
        if previous is None or previous.asset_id is None:
            return DeduplicationDecision(
                DeduplicationResult.NEW_ASSET,
                None,
                0.0,
                {"reason": "no_geolocation_no_prior_track"},
            )
        return DeduplicationDecision(
            DeduplicationResult.MATCHED,
            str(previous.asset_id),
            1.0,
            {"reason": "tracking_id_match_without_geolocation", "tracking_id": tracking_id},
        )
