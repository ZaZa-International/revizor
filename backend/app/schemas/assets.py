from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.domain.enums import (
    ConditionChangeSource,
    DeduplicationResult,
    DefectStatus,
    GeolocationSource,
    GeolocationStatus,
    LifecycleStatus,
    ObservationReviewStatus,
    PriorityBand,
    ReviewDecision,
)


class LocationInput(BaseModel):
    longitude: float = Field(ge=-180, le=180)
    latitude: float = Field(ge=-90, le=90)
    accuracy_m: float | None = Field(default=None, ge=0)


class AssetResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    external_id: str | None
    asset_type: str
    display_name: str | None
    longitude: float | None = None
    latitude: float | None = None
    location_accuracy_m: float | None
    geolocation_status: GeolocationStatus
    current_condition: str | None
    current_severity: int | None
    current_priority: float | None
    priority_band: PriorityBand | None
    priority_factors: dict[str, Any] | None
    priority_policy_version: str | None
    priority_override: float | None
    priority_override_reason: str | None
    lifecycle_status: LifecycleStatus
    first_observed_at: datetime | None
    last_observed_at: datetime | None
    version: int
    created_at: datetime
    updated_at: datetime


class AssetPatchRequest(BaseModel):
    display_name: str | None = Field(default=None, max_length=255)
    external_id: str | None = Field(default=None, max_length=128)
    lifecycle_status: LifecycleStatus | None = None
    priority_override: float | None = Field(default=None, ge=0, le=100)
    priority_override_reason: str | None = None
    location: LocationInput | None = None
    expected_version: int | None = None

    @model_validator(mode="after")
    def _not_empty(self) -> AssetPatchRequest:
        if not any(
            getattr(self, field) is not None
            for field in (
                "display_name",
                "external_id",
                "lifecycle_status",
                "priority_override",
                "location",
            )
        ):
            raise ValueError("At least one field must be provided")
        return self


class ObservationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    asset_id: uuid.UUID | None
    processing_job_id: uuid.UUID
    frame_id: str | None
    detection_id: uuid.UUID | None
    observed_at: datetime
    detected_at: datetime
    object_type: str
    condition_class: str | None
    detector_confidence: float
    classifier_confidence: float | None
    severity: int | None
    bbox: dict[str, Any] | None
    image_width: int | None
    image_height: int | None
    image_id: uuid.UUID | None
    crop_image_id: uuid.UUID | None
    longitude: float | None = None
    latitude: float | None = None
    location_accuracy_m: float | None
    geolocation_status: GeolocationStatus
    geolocation_source: GeolocationSource
    tracking_id: str | None
    model_name: str | None
    model_version: str | None
    dedup_result: DeduplicationResult | None
    dedup_score: float | None
    dedup_explanation: dict[str, Any] | None
    review_status: ObservationReviewStatus
    effective_asset_type: str | None
    effective_condition: str | None
    effective_severity: int | None
    created_at: datetime
    image_url: str | None = None
    crop_url: str | None = None


class DefectResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    asset_id: uuid.UUID
    defect_type: str
    description: str | None
    severity: int
    status: DefectStatus
    first_detected_at: datetime
    last_detected_at: datetime
    resolved_at: datetime | None
    created_at: datetime
    updated_at: datetime
    observation_count: int | None = None


class DefectPatchRequest(BaseModel):
    status: DefectStatus | None = None
    severity: int | None = Field(default=None, ge=1, le=5)
    description: str | None = None

    @model_validator(mode="after")
    def _not_empty(self) -> DefectPatchRequest:
        if self.status is None and self.severity is None and self.description is None:
            raise ValueError("At least one field must be provided")
        return self


class ReviewCreateRequest(BaseModel):
    observation_id: uuid.UUID | None = None
    defect_id: uuid.UUID | None = None
    decision: ReviewDecision
    corrected_asset_type: str | None = Field(default=None, max_length=64)
    corrected_condition: str | None = Field(default=None, max_length=64)
    corrected_defect_type: str | None = Field(default=None, max_length=64)
    corrected_severity: int | None = Field(default=None, ge=1, le=5)
    comment: str | None = Field(default=None, max_length=4000)
    reviewed_at: datetime | None = None

    @model_validator(mode="after")
    def _target(self) -> ReviewCreateRequest:
        if self.observation_id is None and self.defect_id is None:
            raise ValueError("observation_id or defect_id is required")
        return self


class ReviewResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    observation_id: uuid.UUID | None
    defect_id: uuid.UUID | None
    reviewer_id: uuid.UUID
    decision: ReviewDecision
    corrected_asset_type: str | None
    corrected_condition: str | None
    corrected_defect_type: str | None
    corrected_severity: int | None
    comment: str | None
    reviewed_at: datetime
    created_at: datetime


class ConditionHistoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    asset_id: uuid.UUID
    observation_id: uuid.UUID | None
    review_id: uuid.UUID | None
    change_source: ConditionChangeSource
    previous_condition: str | None
    new_condition: str | None
    previous_severity: int | None
    new_severity: int | None
    previous_priority: float | None
    new_priority: float | None
    is_physical_change: bool
    note: str | None
    detected_at: datetime
