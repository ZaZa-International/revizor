"""Review workflow integration: append-only history, corrections, training data."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from app.application.services.history import AssetHistoryService
from app.application.services.reviews import ReviewService
from app.application.services.risk import RiskScoringService
from app.core.security import hash_password
from app.domain.enums import (
    ConditionChangeSource,
    DefectStatus,
    GeolocationStatus,
    ObservationReviewStatus,
    ReviewDecision,
    TrainingExampleStatus,
    UserRole,
)
from app.domain.reviews.logic import ReviewCorrection
from app.infrastructure.database.models.asset import Asset
from app.infrastructure.database.models.defect import Defect, defect_observations
from app.infrastructure.database.models.history import AssetConditionHistory
from app.infrastructure.database.models.job import ProcessingJob
from app.infrastructure.database.models.observation import Observation
from app.infrastructure.database.models.review import Review
from app.infrastructure.database.models.stored_file import StoredFile
from app.infrastructure.database.models.training import TrainingExample
from app.infrastructure.database.models.upload import Upload
from app.infrastructure.database.models.user import User
from sqlalchemy import func, select

pytestmark = pytest.mark.integration


async def _seed_observation_with_defect(database):
    now = datetime.now(UTC)
    async with database.session() as session:
        reviewer = User(
            username=f"reviewer-{uuid.uuid4().hex[:8]}",
            password_hash=hash_password("x"),
            role=UserRole.OPERATOR,
        )
        session.add(reviewer)
        await session.flush()
        upload = Upload(
            original_filename="x.jpg",
            storage_key=f"uploads/{uuid.uuid4()}/x.jpg",
            content_type="image/jpeg",
            file_size=1,
            checksum_sha256=uuid.uuid4().hex + uuid.uuid4().hex,
            media_type="IMAGE",
            metadata_={},
        )
        session.add(upload)
        await session.flush()
        job = ProcessingJob(upload_id=upload.id, status="COMPLETED")
        session.add(job)
        await session.flush()
        stored = StoredFile(
            storage_key=f"frames/{uuid.uuid4()}/0.jpg",
            kind="FRAME",
            upload_id=upload.id,
            content_type="image/jpeg",
            file_size=1,
            width=640,
            height=480,
        )
        session.add(stored)
        await session.flush()
        asset = Asset(
            asset_type="telecom_well",
            geolocation_status=GeolocationStatus.UNAVAILABLE,
            current_condition="damaged_cover",
            current_severity=4,
            current_priority=80.0,
        )
        session.add(asset)
        await session.flush()
        observation = Observation(
            asset_id=asset.id,
            processing_job_id=job.id,
            image_id=stored.id,
            observed_at=now,
            detected_at=now,
            object_type="telecom_well",
            condition_class="damaged_cover",
            detector_confidence=0.9,
            severity=4,
            geolocation_status=GeolocationStatus.UNAVAILABLE,
            effective_asset_type="telecom_well",
            effective_condition="damaged_cover",
            effective_severity=4,
        )
        session.add(observation)
        await session.flush()
        defect = Defect(
            asset_id=asset.id,
            defect_type="damaged_cover",
            severity=4,
            status=DefectStatus.OPEN,
            first_detected_at=now,
            last_detected_at=now,
        )
        session.add(defect)
        await session.flush()
        await session.execute(
            defect_observations.insert().values(defect_id=defect.id, observation_id=observation.id)
        )
        await session.commit()
        return observation.id, asset.id, defect.id, reviewer.id


async def test_confirm_review_updates_defect_and_creates_training_example(database, settings):
    observation_id, _asset_id, defect_id, reviewer_id = await _seed_observation_with_defect(
        database
    )
    async with database.session() as session:
        service = ReviewService(session, RiskScoringService(settings), AssetHistoryService(session))
        review = await service.create_review(
            observation_id=observation_id,
            defect_id=None,
            reviewer_id=reviewer_id,
            decision=ReviewDecision.CONFIRMED,
            correction=ReviewCorrection(),
            comment="looks right",
        )
        await session.commit()
        review_id = review.id

    async with database.session() as session:
        obs = await session.get(Observation, observation_id)
        assert obs.review_status == ObservationReviewStatus.CONFIRMED
        assert obs.condition_class == "damaged_cover"
        defect = await session.get(Defect, defect_id)
        assert defect.status == DefectStatus.CONFIRMED
        example = (
            await session.execute(
                select(TrainingExample).where(TrainingExample.observation_id == observation_id)
            )
        ).scalar_one()
        assert example.status == TrainingExampleStatus.PENDING
        assert example.label["object_type"] == "telecom_well"
        history = (
            (
                await session.execute(
                    select(AssetConditionHistory).where(
                        AssetConditionHistory.review_id == review_id
                    )
                )
            )
            .scalars()
            .all()
        )
        assert any(h.change_source == ConditionChangeSource.HUMAN_REVIEW for h in history)
        assert all(h.is_physical_change for h in history)


async def test_repeated_reviews_are_append_only(database, settings):
    observation_id, asset_id, _, reviewer_id = await _seed_observation_with_defect(database)
    async with database.session() as session:
        service = ReviewService(session, RiskScoringService(settings), AssetHistoryService(session))
        await service.create_review(
            observation_id=observation_id,
            defect_id=None,
            reviewer_id=reviewer_id,
            decision=ReviewDecision.CONFIRMED,
            correction=ReviewCorrection(),
            comment=None,
        )
        await service.create_review(
            observation_id=observation_id,
            defect_id=None,
            reviewer_id=reviewer_id,
            decision=ReviewDecision.CORRECTED,
            correction=ReviewCorrection(corrected_severity=2, corrected_condition="ok"),
            comment="actually minor",
        )
        await session.commit()

    async with database.session() as session:
        count = (
            await session.execute(
                select(func.count(Review.id)).where(Review.observation_id == observation_id)
            )
        ).scalar_one()
        assert count == 2
        obs = await session.get(Observation, observation_id)
        assert obs.review_status == ObservationReviewStatus.CORRECTED
        assert obs.effective_severity == 2
        assert obs.effective_condition == "ok"
        assert obs.severity == 4
        asset = await session.get(Asset, asset_id)
        assert asset.current_severity == 2
        assert asset.current_condition == "ok"


async def test_reject_single_observation_rejects_defect(database, settings):
    observation_id, _, defect_id, reviewer_id = await _seed_observation_with_defect(database)
    async with database.session() as session:
        service = ReviewService(session, RiskScoringService(settings), AssetHistoryService(session))
        await service.create_review(
            observation_id=observation_id,
            defect_id=None,
            reviewer_id=reviewer_id,
            decision=ReviewDecision.REJECTED,
            correction=ReviewCorrection(),
            comment="false positive",
        )
        await session.commit()
    async with database.session() as session:
        defect = await session.get(Defect, defect_id)
        assert defect.status == DefectStatus.REJECTED
        obs = await session.get(Observation, observation_id)
        assert obs.review_status == ObservationReviewStatus.REJECTED
        assert obs.condition_class == "damaged_cover"
