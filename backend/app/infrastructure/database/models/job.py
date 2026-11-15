from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.domain.enums import FrameStatus, JobStatus, ProcessingStage
from app.infrastructure.database.base import (
    Base,
    CreatedAtMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)

if TYPE_CHECKING:
    from app.infrastructure.database.models.route import Route
    from app.infrastructure.database.models.upload import Upload


class ProcessingJob(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "processing_jobs"
    __table_args__ = (
        CheckConstraint("progress >= 0 AND progress <= 1", name="progress_range"),
        CheckConstraint("total_frames >= 0", name="total_frames_nonneg"),
        CheckConstraint("processed_frames >= 0", name="processed_frames_nonneg"),
        CheckConstraint("failed_frames >= 0", name="failed_frames_nonneg"),
        CheckConstraint("rejected_frames >= 0", name="rejected_frames_nonneg"),
    )

    upload_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("uploads.id", ondelete="CASCADE"), nullable=False, index=True
    )
    route_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("routes.id", ondelete="SET NULL"), nullable=True, index=True
    )
    status: Mapped[JobStatus] = mapped_column(
        Enum(JobStatus, name="job_status"), nullable=False, default=JobStatus.PENDING, index=True
    )
    progress: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    current_stage: Mapped[ProcessingStage | None] = mapped_column(
        Enum(ProcessingStage, name="processing_stage"), nullable=True
    )
    total_frames: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    processed_frames: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_frames: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rejected_frames: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    started_at: Mapped[datetime | None] = mapped_column(nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), unique=True, nullable=True)
    rq_job_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    options: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    upload: Mapped[Upload] = relationship(back_populates="jobs")
    route: Mapped[Route | None] = relationship(back_populates="jobs")
    frames: Mapped[list[JobFrame]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )


class JobFrame(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """Per-frame processing record: idempotency anchor and progress source."""

    __tablename__ = "job_frames"
    __table_args__ = (UniqueConstraint("job_id", "frame_index", name="uq_job_frame_index"),)

    job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("processing_jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    frame_index: Mapped[int] = mapped_column(Integer, nullable=False)
    stored_file_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("stored_files.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[FrameStatus] = mapped_column(
        Enum(FrameStatus, name="frame_status"), nullable=False, index=True
    )
    reject_reason: Mapped[str | None] = mapped_column(String(128), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    observed_at: Mapped[datetime | None] = mapped_column(nullable=True)

    job: Mapped[ProcessingJob] = relationship(back_populates="frames")
