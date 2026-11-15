from __future__ import annotations

import uuid

from sqlalchemy import BigInteger, Enum, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.enums import AnonymizationStatus, StorageObjectKind
from app.infrastructure.database.base import Base, CreatedAtMixin, UUIDPrimaryKeyMixin


class StoredFile(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """Metadata of a file in object storage. Binary content never lives in PostgreSQL."""

    __tablename__ = "stored_files"

    storage_key: Mapped[str] = mapped_column(String(1024), unique=True, nullable=False)
    kind: Mapped[StorageObjectKind] = mapped_column(
        Enum(StorageObjectKind, name="storage_object_kind"), nullable=False, index=True
    )
    upload_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("uploads.id", ondelete="CASCADE"), nullable=True, index=True
    )
    content_type: Mapped[str] = mapped_column(String(128), nullable=False)
    file_size: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    checksum_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    anonymization_status: Mapped[AnonymizationStatus] = mapped_column(
        Enum(AnonymizationStatus, name="anonymization_status"),
        nullable=False,
        default=AnonymizationStatus.NOT_APPLIED,
    )
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict)
