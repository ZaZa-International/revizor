from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Enum, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.enums import TrainingExampleStatus
from app.infrastructure.database.base import Base, CreatedAtMixin, UUIDPrimaryKeyMixin


class TrainingExample(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """Verified (image, label) pair accumulated for controlled active learning."""

    __tablename__ = "training_examples"

    observation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("observations.id", ondelete="RESTRICT"), unique=True, nullable=False
    )
    review_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("reviews.id", ondelete="RESTRICT"), nullable=False
    )
    image_storage_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    label: Mapped[dict] = mapped_column(JSONB, nullable=False)
    status: Mapped[TrainingExampleStatus] = mapped_column(
        Enum(TrainingExampleStatus, name="training_example_status"),
        nullable=False,
        default=TrainingExampleStatus.PENDING,
        index=True,
    )
    exported_at: Mapped[datetime | None] = mapped_column(nullable=True)
