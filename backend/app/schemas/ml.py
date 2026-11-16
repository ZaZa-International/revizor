"""ML integration contracts (schema_version 1.0).

These Pydantic models are the ONLY shared vocabulary between backend and ML
services. Backend domain models never import ML frameworks. Coordinate system:
bbox is in ABSOLUTE PIXEL coordinates of the source image (origin top-left).
Geographic coordinates are ALWAYS (longitude, latitude), WGS84 / SRID 4326.
"""
# ruff: noqa: RUF001, RUF002  # русскоязычная документация API: кириллица и тире намеренны (ложные срабатывания)

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Final, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

ML_SCHEMA_VERSION: Final = "1.0"


class MLImageRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    storage_key: str = Field(min_length=1, max_length=1024)
    width: int = Field(gt=0, le=32768)
    height: int = Field(gt=0, le=32768)
    checksum_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")


class MLFrameMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    observed_at: datetime | None = None
    longitude: float | None = Field(default=None, ge=-180, le=180)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    heading_deg: float | None = Field(default=None, ge=0, lt=360)
    speed_mps: float | None = Field(default=None, ge=0)
    route_id: str | None = None
    frame_index: int | None = Field(default=None, ge=0)
    tracking_id: str | None = None

    @model_validator(mode="after")
    def _coords_pair(self) -> MLFrameMetadata:
        if (self.longitude is None) != (self.latitude is None):
            raise ValueError("longitude and latitude must be provided together")
        return self


class MLInferenceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = ML_SCHEMA_VERSION
    request_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    image: MLImageRef
    metadata: MLFrameMetadata = Field(default_factory=MLFrameMetadata)


class MLBBox(BaseModel):
    """Absolute pixel coordinates, origin top-left of the source image."""

    model_config = ConfigDict(extra="forbid")

    x_min: float = Field(ge=0)
    y_min: float = Field(ge=0)
    x_max: float = Field(gt=0)
    y_max: float = Field(gt=0)

    @model_validator(mode="after")
    def _ordered(self) -> MLBBox:
        if self.x_min >= self.x_max or self.y_min >= self.y_max:
            raise ValueError("bbox min must be strictly less than max")
        return self


class MLDetection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    detection_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    object_type: str = Field(min_length=1, max_length=64)
    condition_class: str | None = Field(default=None, max_length=64)
    confidence: float = Field(ge=0, le=1)
    severity: int | None = Field(default=None, ge=1, le=5)
    bbox: MLBBox
    embedding: list[float] | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)


class MLModelInfo(BaseModel):
    """Идентификация активной ML-модели (контракт v1.0)."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {"name": "infrastructure-detector", "version": "1.2.0", "schema_version": "1.0"}
            ]
        },
    )

    name: str = Field(description="Имя модели", examples=["infrastructure-detector"])
    version: str = Field(description="Версия модели", examples=["1.2.0"])
    schema_version: str = Field(
        default=ML_SCHEMA_VERSION, description="Версия ML-контракта", examples=["1.0"]
    )


class MLInferenceResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = ML_SCHEMA_VERSION
    request_id: uuid.UUID
    model: MLModelInfo
    detections: list[MLDetection] = Field(default_factory=list)
    inference_time_ms: float | None = Field(default=None, ge=0)

    @field_validator("detections")
    @classmethod
    def _unique_detection_ids(cls, value: list[MLDetection]) -> list[MLDetection]:
        ids = [d.detection_id for d in value]
        if len(set(ids)) != len(ids):
            raise ValueError("detection_id must be unique within a response")
        return value


class MLItemError(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    message: str


class MLBatchItemResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: uuid.UUID
    status: Literal["OK", "ERROR"]
    response: MLInferenceResponse | None = None
    error: MLItemError | None = None

    @model_validator(mode="after")
    def _consistency(self) -> MLBatchItemResult:
        if self.status == "OK" and self.response is None:
            raise ValueError("OK batch item must carry a response")
        if self.status == "ERROR" and self.error is None:
            raise ValueError("ERROR batch item must carry an error")
        return self


class MLBatchResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = ML_SCHEMA_VERSION
    model: MLModelInfo
    results: list[MLBatchItemResult]


class MLHealth(BaseModel):
    """Здоровье ML-провайдера со стороны backend (GET /api/v1/ml/health)."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {"status": "ok", "model_loaded": True, "provider": "http", "details": {}},
                {
                    "status": "unavailable",
                    "model_loaded": False,
                    "provider": "http",
                    "details": {"error": "ml_unavailable"},
                },
            ]
        },
    )

    status: Literal["ok", "degraded", "unavailable"] = Field(
        description="ok — провайдер доступен; degraded — работает с ограничениями; "
        "unavailable — недоступен"
    )
    model_loaded: bool = Field(description="Загружена ли модель на стороне провайдера")
    provider: str = Field(description="Провайдер: mock / http", examples=["http"])
    details: dict[str, Any] = Field(
        default_factory=dict, description="Дополнительные детали (код ошибки при отказе)"
    )
