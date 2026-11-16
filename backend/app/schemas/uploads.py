# ruff: noqa: RUF001, RUF002  # русскоязычная документация API: кириллица и тире намеренны (ложные срабатывания)
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

_UPLOAD_EXAMPLE: dict[str, Any] = {
    "id": "a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d",
    "original_filename": "well_0001.jpg",
    "storage_key": "uploads/2026/11/15/a1b2c3d4_well_0001.jpg",
    "content_type": "image/jpeg",
    "file_size": 245760,
    "checksum_sha256": "9f2c4e7a1b3d5f8092a4c6e8d0f1a3b5c7d9e1f3a5b7c9d1e3f5a7b9c1d3e5f7",
    "media_type": "IMAGE",
    "uploaded_by": "f6a7b8c9-d0e1-4f2a-3b4c-5d6e7f809102",
    "route_id": "d4e5f6a7-b8c9-4d0e-1f2a-3b4c5d6e7f80",
    "metadata": {
        "capture_started_at": "2026-11-15T12:00:00Z",
        "gps_track": [
            {
                "timestamp": "2026-11-15T12:00:00Z",
                "longitude": 37.6173,
                "latitude": 55.7558,
                "accuracy_m": 4.0,
                "heading_deg": 45.0,
                "speed_mps": 8.0,
            }
        ],
    },
    "created_at": "2026-11-15T12:01:00Z",
    "presigned_url": "http://localhost:9000/mgts-infra/uploads/2026/11/15/a1b2c3d4_well_0001.jpg"
    "?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Expires=3600",
}


class UploadResponse(BaseModel):
    """Загруженный файл. Для дубликата чужого файла поля original_filename/storage_key
    заменяются на '[redacted]', metadata очищается, uploaded_by/route_id = null,
    presigned_url не выдаётся (см. docs/api/upload-and-processing.md)."""

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        json_schema_extra={"examples": [_UPLOAD_EXAMPLE]},
    )

    id: uuid.UUID = Field(description="Идентификатор загрузки (UUID)")
    original_filename: str = Field(
        description="Исходное имя файла (sanitized); '[redacted]' для чужого дубликата",
        examples=["well_0001.jpg"],
    )
    storage_key: str = Field(
        description="Ключ объекта в хранилище; '[redacted]' для чужого дубликата",
        examples=["uploads/2026/11/15/a1b2c3d4_well_0001.jpg"],
    )
    content_type: str = Field(description="MIME-тип файла", examples=["image/jpeg"])
    file_size: int = Field(description="Размер файла в байтах", examples=[245760])
    checksum_sha256: str = Field(
        description="SHA-256 содержимого; ключ дедупликации (UNIQUE)",
        examples=["9f2c4e7a1b3d5f8092a4c6e8d0f1a3b5c7d9e1f3a5b7c9d1e3f5a7b9c1d3e5f7"],
    )
    media_type: MediaType = Field(description="IMAGE или VIDEO (по magic bytes)")
    uploaded_by: uuid.UUID | None = Field(description="Кто загрузил; null для чужого дубликата")
    route_id: uuid.UUID | None = Field(description="Привязанный маршрут объезда (опционально)")
    metadata: dict[str, Any] = Field(
        validation_alias="metadata_",
        description="Произвольные метаданные JSON: gps_track, capture_started_at и др.; "
        "{} для чужого дубликата",
    )
    created_at: datetime = Field(description="Дата загрузки (ISO 8601, UTC)")
    presigned_url: str | None = Field(
        default=None,
        description="Временная ссылка на файл (S3 presigned GET, TTL по умолчанию 3600 с); "
        "null для VIEWER, чужих дубликатов и local storage",
    )


class UploadCreateResponse(BaseModel):
    """Результат POST /uploads: 201 — новый файл (created=true),
    200 — дубликат по checksum (created=false, возможна редакция чужих данных)."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {"upload": _UPLOAD_EXAMPLE, "created": True},
                {"upload": _UPLOAD_EXAMPLE, "created": False},
            ]
        }
    )

    upload: UploadResponse = Field(description="Созданная или найденная загрузка")
    created: bool = Field(
        description="true — файл создан (201); false — дубликат по checksum (200)"
    )


class JobCreateRequest(BaseModel):
    """Запрос на создание processing job для загрузки."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "upload_id": "a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d",
                    "route_id": "d4e5f6a7-b8c9-4d0e-1f2a-3b4c5d6e7f80",
                    "options": {},
                }
            ]
        }
    )

    upload_id: uuid.UUID = Field(description="Идентификатор загрузки для обработки")
    route_id: uuid.UUID | None = Field(
        default=None,
        description="Маршрут объезда; если не задан, наследуется route_id загрузки",
    )
    options: dict[str, Any] = Field(
        default_factory=dict,
        description="Reserved for processing overrides; currently informational",
    )


class JobResponse(BaseModel):
    """Processing job: статус, прогресс и счётчики кадров. Опрос каждые 1–2 с
    до терминального статуса (COMPLETED/PARTIALLY_COMPLETED/FAILED/CANCELLED)."""

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "examples": [
                {
                    "id": "b2c3d4e5-f6a7-4b8c-9d0e-1f2a3b4c5d6e",
                    "upload_id": "a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d",
                    "route_id": "d4e5f6a7-b8c9-4d0e-1f2a-3b4c5d6e7f80",
                    "status": "PROCESSING",
                    "progress": 0.45,
                    "current_stage": "INFERENCE",
                    "total_frames": 120,
                    "processed_frames": 54,
                    "failed_frames": 0,
                    "rejected_frames": 2,
                    "started_at": "2026-11-15T12:02:00Z",
                    "finished_at": None,
                    "error_code": None,
                    "error_message": None,
                    "created_at": "2026-11-15T12:01:30Z",
                    "updated_at": "2026-11-15T12:03:10Z",
                }
            ]
        },
    )

    id: uuid.UUID = Field(description="Идентификатор job (UUID)")
    upload_id: uuid.UUID = Field(description="Обрабатываемая загрузка")
    route_id: uuid.UUID | None = Field(description="Маршрут объезда (наследуется от загрузки)")
    status: JobStatus = Field(description="Статус жизненного цикла job")
    progress: float = Field(
        description="Прогресс обработки 0.0–1.0 (доля обработанных кадров)", examples=[0.45]
    )
    current_stage: ProcessingStage | None = Field(
        description="Текущая стадия pipeline (информационно)"
    )
    total_frames: int = Field(
        description="Всего кадров (оценка для видео, уточняется)", examples=[120]
    )
    processed_frames: int = Field(description="Успешно обработано кадров", examples=[54])
    failed_frames: int = Field(description="Кадров с ошибкой обработки", examples=[0])
    rejected_frames: int = Field(description="Кадров, отбракованных quality gate", examples=[2])
    started_at: datetime | None = Field(description="Начало обработки worker'ом")
    finished_at: datetime | None = Field(description="Завершение (терминальные статусы)")
    error_code: str | None = Field(
        description="Машинный код ошибки job (queue_unavailable, stale_processing, ...)",
        examples=["queue_unavailable"],
    )
    error_message: str | None = Field(description="Описание ошибки job (для диагностики)")
    created_at: datetime = Field(description="Дата создания job")
    updated_at: datetime = Field(
        description="Последнее обновление; используется для определения «зависших» PROCESSING"
    )


class JobFrameResponse(BaseModel):
    """Покадровый результат job (порядок по frame_index)."""

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "examples": [
                {
                    "id": "0a1b2c3d-4e5f-4a6b-7c8d-9e0f1a2b3c4d",
                    "frame_index": 7,
                    "status": "PROCESSED",
                    "reject_reason": None,
                    "error_code": None,
                    "observed_at": "2026-11-15T12:00:07Z",
                },
                {
                    "id": "1b2c3d4e-5f6a-4b7c-8d9e-0f1a2b3c4d5e",
                    "frame_index": 8,
                    "status": "REJECTED",
                    "reject_reason": "blur",
                    "error_code": None,
                    "observed_at": "2026-11-15T12:00:08Z",
                },
            ]
        },
    )

    id: uuid.UUID = Field(description="Идентификатор записи кадра (UUID)")
    frame_index: int = Field(description="Порядковый номер кадра (0-based)", examples=[7])
    status: FrameStatus = Field(description="PROCESSED / REJECTED / FAILED / SKIPPED")
    reject_reason: str | None = Field(
        description="Причина отбраковки quality gate (blur, overexposure, ...)", examples=["blur"]
    )
    error_code: str | None = Field(description="Код ошибки обработки кадра (ml_timeout, ...)")
    observed_at: datetime | None = Field(description="Время кадра из GPS-трека (если доступно)")


class StoredFileResponse(BaseModel):
    """Файл в хранилище (кадр, кроп, оригинал, анонимизированная версия)."""

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "examples": [
                {
                    "id": "0a1b2c3d-4e5f-4a6b-7c8d-9e0f1a2b3c4d",
                    "storage_key": "frames/b2c3d4e5/frame_000007.jpg",
                    "kind": "FRAME",
                    "content_type": "image/jpeg",
                    "file_size": 184320,
                    "width": 1920,
                    "height": 1080,
                    "anonymization_status": "NOT_APPLIED",
                    "url": None,
                }
            ]
        },
    )

    id: uuid.UUID = Field(description="Идентификатор файла (UUID)")
    storage_key: str = Field(description="Ключ объекта в хранилище")
    kind: str = Field(description="Вид файла: ORIGINAL / FRAME / CROP / ANONYMIZED / EXPORT")
    content_type: str = Field(description="MIME-тип", examples=["image/jpeg"])
    file_size: int = Field(description="Размер в байтах", examples=[184320])
    width: int | None = Field(description="Ширина изображения в пикселях", examples=[1920])
    height: int | None = Field(description="Высота изображения в пикселях", examples=[1080])
    anonymization_status: AnonymizationStatus = Field(
        description="Статус анонимизации; NOT_APPLIED означает, что обработка не выполнялась"
    )
    url: str | None = Field(default=None, description="Ссылка на файл (presigned или /files)")
