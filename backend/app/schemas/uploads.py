from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.domain.enums import (
    AnonymizationStatus,
    FrameStatus,
    JobStatus,
    MediaType,
    ProcessingStage,
)


class UploadResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: uuid.UUID
    original_filename: str
    storage_key: str
    content_type: str
    file_size: int
    checksum_sha256: str
    media_type: MediaType
    uploaded_by: uuid.UUID | None
    route_id: uuid.UUID | None
    metadata: dict[str, Any] = Field(validation_alias="metadata_")
    created_at: datetime
    presigned_url: str | None = None


class UploadCreateResponse(BaseModel):
    upload: UploadResponse
    created: bool


class JobCreateRequest(BaseModel):
    upload_id: uuid.UUID
    route_id: uuid.UUID | None = None
    options: dict[str, Any] = Field(default_factory=dict)


class JobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    upload_id: uuid.UUID
    route_id: uuid.UUID | None
    status: JobStatus
    progress: float
    current_stage: ProcessingStage | None
    total_frames: int
    processed_frames: int
    failed_frames: int
    rejected_frames: int
    started_at: datetime | None
    finished_at: datetime | None
    error_code: str | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime


class JobFrameResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    frame_index: int
    status: FrameStatus
    reject_reason: str | None
    error_code: str | None
    observed_at: datetime | None


class StoredFileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    storage_key: str
    kind: str
    content_type: str
    file_size: int
    width: int | None
    height: int | None
    anonymization_status: AnonymizationStatus
    url: str | None = None
