from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from geoalchemy2 import Geography
from sqlalchemy import (
    CheckConstraint,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.domain.enums import (
    DeduplicationResult,
    GeolocationSource,
    GeolocationStatus,
    ObservationReviewStatus,
)
from app.infrastructure.database.base import Base, CreatedAtMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.infrastructure.database.models.asset import Asset
    from app.infrastructure.database.models.job import JobFrame, ProcessingJob
    from app.infrastructure.database.models.stored_file import StoredFile


class Observation(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """A single detection of a physical object on a specific frame.

    Stored regardless of human confirmation. Original ML output is immutable;
    human corrections live in reviews + effective_* fields.
    """

    __tablename__ = "observations"
    __table_args__ = (
        CheckConstraint(
            "detector_confidence >= 0 AND detector_confidence <= 1",
            name="detector_confidence_range",
        ),
        CheckConstraint(
            "classifier_confidence IS NULL OR "
            "(classifier_confidence >= 0 AND classifier_confidence <= 1)",
            name="classifier_confidence_range",
        ),
        CheckConstraint(
            "severity IS NULL OR (severity >= 1 AND severity <= 5)", name="severity_range"
        ),
        CheckConstraint(
            "(location IS NULL) = (geolocation_status IN ('UNAVAILABLE', 'INVALID'))",
            name="location_matches_status",
        ),
        Index(
            "uq_observations_job_detection",
            "processing_job_id",
            "detection_id",
            unique=True,
            postgresql_where="detection_id IS NOT NULL",
        ),
    )

    asset_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("assets.id", ondelete="SET NULL"), nullable=True, index=True
    )
    processing_job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("processing_jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    job_frame_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("job_frames.id", ondelete="SET NULL"), nullable=True
    )
    frame_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    detection_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    observed_at: Mapped[datetime] = mapped_column(nullable=False, index=True)
    detected_at: Mapped[datetime] = mapped_column(nullable=False)
    object_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    condition_class: Mapped[str | None] = mapped_column(String(64), nullable=True)
    detector_confidence: Mapped[float] = mapped_column(Float, nullable=False)
    classifier_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    severity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    bbox: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    image_width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    image_height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    image_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("stored_files.id", ondelete="SET NULL"), nullable=True
    )
    crop_image_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("stored_files.id", ondelete="SET NULL"), nullable=True
    )
    location: Mapped[str | None] = mapped_column(
        Geography(geometry_type="POINT", srid=4326), nullable=True
    )
    location_accuracy_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    geolocation_status: Mapped[GeolocationStatus] = mapped_column(
        Enum(GeolocationStatus, name="geolocation_status"),
        nullable=False,
        default=GeolocationStatus.UNAVAILABLE,
        index=True,
    )
    geolocation_source: Mapped[GeolocationSource] = mapped_column(
        Enum(GeolocationSource, name="geolocation_source"),
        nullable=False,
        default=GeolocationSource.UNKNOWN,
    )
    heading_deg: Mapped[float | None] = mapped_column(Float, nullable=True)
    speed_mps: Mapped[float | None] = mapped_column(Float, nullable=True)
    tracking_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    model_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    model_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    raw_model_payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    dedup_result: Mapped[DeduplicationResult | None] = mapped_column(
        Enum(DeduplicationResult, name="deduplication_result"), nullable=True, index=True
    )
    dedup_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    dedup_explanation: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    review_status: Mapped[ObservationReviewStatus] = mapped_column(
        Enum(ObservationReviewStatus, name="observation_review_status"),
        nullable=False,
        default=ObservationReviewStatus.UNREVIEWED,
        index=True,
    )
    effective_asset_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    effective_condition: Mapped[str | None] = mapped_column(String(64), nullable=True)
    effective_severity: Mapped[int | None] = mapped_column(Integer, nullable=True)

    asset: Mapped[Asset | None] = relationship(back_populates="observations")
    job: Mapped[ProcessingJob] = relationship()
    job_frame: Mapped[JobFrame | None] = relationship()
    image: Mapped[StoredFile | None] = relationship(foreign_keys=[image_id])
    crop_image: Mapped[StoredFile | None] = relationship(foreign_keys=[crop_image_id])
