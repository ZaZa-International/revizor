# ruff: noqa: RUF001, RUF002  # русскоязычная документация API: кириллица и тире намеренны (ложные срабатывания)
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
    """Ручная геопривязка объекта (PATCH asset). Порядок координат: longitude, latitude."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [{"longitude": 37.6173, "latitude": 55.7558, "accuracy_m": 5.0}]
        }
    )

    longitude: float = Field(ge=-180, le=180, description="Долгота (WGS84)", examples=[37.6173])
    latitude: float = Field(ge=-90, le=90, description="Широта (WGS84)", examples=[55.7558])
    accuracy_m: float | None = Field(
        default=None, ge=0, description="Оценка точности в метрах (опционально)", examples=[5.0]
    )


class AssetResponse(BaseModel):
    """Физический объект инфраструктуры в реестре (колодец, опора, шкаф, кабельная линия).

    current_priority 0–100 рассчитывается внутренней risk-политикой (не отраслевой
    стандарт); факторы сохраняются в priority_factors. version используется для
    оптимистичной блокировки PATCH (expected_version)."""

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "examples": [
                {
                    "id": "3f2b8c1e-9d4a-4f6b-8e2c-1a5d7b9f0c34",
                    "external_id": "MGTS-W-001234",
                    "asset_type": "telecom_well",
                    "display_name": "Колодец у дома 12 по ул. Тверская",
                    "longitude": 37.6173,
                    "latitude": 55.7558,
                    "location_accuracy_m": 4.0,
                    "geolocation_status": "CONFIRMED",
                    "current_condition": "missing_cover",
                    "current_severity": 5,
                    "current_priority": 87.5,
                    "priority_band": "HIGH_PRIORITY",
                    "priority_factors": {
                        "policy_version": "1.0",
                        "severity_weight": 0.4,
                        "confidence_weight": 0.3,
                        "type_weight": 0.3,
                        "severity": 5,
                        "confidence": 0.93,
                    },
                    "priority_policy_version": "1.0",
                    "priority_override": None,
                    "priority_override_reason": None,
                    "lifecycle_status": "ACTIVE",
                    "first_observed_at": "2026-11-15T12:00:00Z",
                    "last_observed_at": "2026-11-15T12:00:00Z",
                    "version": 3,
                    "created_at": "2026-11-15T12:00:05Z",
                    "updated_at": "2026-11-15T12:00:05Z",
                }
            ]
        },
    )

    id: uuid.UUID = Field(description="Идентификатор актива (UUID)")
    external_id: str | None = Field(
        description="Внешний идентификатор (инвентарный номер и т.п.)", examples=["MGTS-W-001234"]
    )
    asset_type: str = Field(
        description="Тип объекта из реестра taxonomy: telecom_well, pole, telecom_cabinet, "
        "cable_line, other",
        examples=["telecom_well"],
    )
    display_name: str | None = Field(
        description="Отображаемое имя (задаётся оператором)",
        examples=["Колодец у дома 12 по ул. Тверская"],
    )
    longitude: float | None = Field(
        default=None, description="Долгота (WGS84); null при geolocation_status=UNAVAILABLE"
    )
    latitude: float | None = Field(
        default=None, description="Широта (WGS84); null при geolocation_status=UNAVAILABLE"
    )
    location_accuracy_m: float | None = Field(description="Точность координат в метрах")
    geolocation_status: GeolocationStatus = Field(description="Достоверность геопривязки")
    current_condition: str | None = Field(
        description="Текущее состояние (канонический словарь condition: ok, damaged, "
        "damaged_cover, missing_cover, door_open, tilted, subsided, cable_sag, "
        "cable_break, unknown)",
        examples=["missing_cover"],
    )
    current_severity: int | None = Field(description="Текущая тяжесть состояния 1–5", examples=[5])
    current_priority: float | None = Field(
        description="Приоритет 0–100 по внутренней risk-политике", examples=[87.5]
    )
    priority_band: PriorityBand | None = Field(description="Полоса приоритета")
    priority_factors: dict[str, Any] | None = Field(
        default=None,
        description="Machine-readable risk factor breakdown persisted with the score "
        "(weights, inputs, policy version); internal scoring policy, not an industry standard",
    )
    priority_policy_version: str | None = Field(
        description="Версия risk-политики, по которой рассчитан приоритет", examples=["1.0"]
    )
    priority_override: float | None = Field(
        description="Ручной приоритет оператора 0–100 (перекрывает расчётный)"
    )
    priority_override_reason: str | None = Field(
        description="Обоснование ручного приоритета; обязательно при priority_override"
    )
    lifecycle_status: LifecycleStatus = Field(description="Жизненный цикл объекта")
    first_observed_at: datetime | None = Field(description="Первое наблюдение объекта")
    last_observed_at: datetime | None = Field(
        description="Последнее наблюдение; поле фильтрации date_from/date_to для /assets"
    )
    version: int = Field(
        description="Версия для оптимистичной блокировки; передавайте в expected_version PATCH",
        examples=[3],
    )
    created_at: datetime = Field(description="Дата создания записи")
    updated_at: datetime = Field(description="Дата последнего обновления")


class AssetPatchRequest(BaseModel):
    """Ручное обновление актива (OPERATOR+). Семантика присутствия полей (exclude_unset):
    явный null очищает значение. Очистка priority_override также очищает
    priority_override_reason; установка priority_override требует
    priority_override_reason в том же PATCH. expected_version — оптимистичная
    блокировка: несовпадение с текущей version → 409 conflict."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "display_name": "Колодец у дома 12 по ул. Тверская",
                    "priority_override": 95.0,
                    "priority_override_reason": "Открытый колодец рядом со школой",
                    "expected_version": 3,
                },
                {
                    "location": {"longitude": 37.6173, "latitude": 55.7558, "accuracy_m": 5.0},
                    "expected_version": 3,
                },
            ]
        }
    )

    display_name: str | None = Field(
        default=None, max_length=255, description="Отображаемое имя; null очищает"
    )
    external_id: str | None = Field(
        default=None, max_length=128, description="Внешний идентификатор; null очищает"
    )
    lifecycle_status: LifecycleStatus | None = Field(
        default=None, description="Жизненный цикл: ACTIVE / INACTIVE / RETIRED / UNKNOWN"
    )
    priority_override: float | None = Field(
        default=None,
        ge=0,
        le=100,
        description="Ручной приоритет 0–100; требует priority_override_reason; null очищает "
        "override вместе с reason",
    )
    priority_override_reason: str | None = Field(
        default=None, max_length=2000, description="Обоснование ручного приоритета"
    )
    location: LocationInput | None = Field(
        default=None,
        description="Ручная геопривязка (longitude, latitude, accuracy_m?); "
        "geolocation_source становится MANUAL",
    )
    expected_version: int | None = Field(
        default=None,
        description="Ожидаемая версия актива (оптимистичная блокировка); "
        "несовпадение → 409 conflict",
        examples=[3],
    )

    @model_validator(mode="after")
    def _not_empty(self) -> AssetPatchRequest:
        if not self.model_fields_set - {"expected_version"}:
            raise ValueError("At least one field must be provided")
        return self


class ObservationResponse(BaseModel):
    """ML-детекция объекта на кадре. Исходное предсказание — object_type/condition_class/
    severity/detector_confidence (никогда не затирается); человеческое решение —
    effective_* и review_status. image_url/crop_url доступны только OPERATOR/SERVICE/ADMIN
    (VIEWER получает null). Параметр запроса job_id соответствует полю processing_job_id."""

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "examples": [
                {
                    "id": "7c1e9a2b-4d5f-4a8c-9b3e-2f6a8d0c1e57",
                    "asset_id": "3f2b8c1e-9d4a-4f6b-8e2c-1a5d7b9f0c34",
                    "processing_job_id": "b2c3d4e5-f6a7-4b8c-9d0e-1f2a3b4c5d6e",
                    "frame_id": "frame_000007",
                    "detection_id": "8d2f0b3c-5e6a-4b9d-0c4f-3a7b9e1d2f68",
                    "observed_at": "2026-11-15T12:00:07Z",
                    "detected_at": "2026-11-15T12:02:30Z",
                    "object_type": "telecom_well",
                    "condition_class": "missing_cover",
                    "detector_confidence": 0.93,
                    "classifier_confidence": 0.88,
                    "severity": 5,
                    "bbox": {"x_min": 812.0, "y_min": 430.0, "x_max": 1040.0, "y_max": 618.0},
                    "image_width": 1920,
                    "image_height": 1080,
                    "image_id": "0a1b2c3d-4e5f-4a6b-7c8d-9e0f1a2b3c4d",
                    "crop_image_id": "1b2c3d4e-5f6a-4b7c-8d9e-0f1a2b3c4d5e",
                    "longitude": 37.6173,
                    "latitude": 55.7558,
                    "location_accuracy_m": 4.0,
                    "geolocation_status": "CONFIRMED",
                    "geolocation_source": "GPS",
                    "tracking_id": "track-0007",
                    "model_name": "mgts-detector",
                    "model_version": "1.0.0",
                    "dedup_result": "MATCHED",
                    "dedup_score": 0.86,
                    "dedup_explanation": {
                        "candidates": [{"asset_id": "3f2b8c1e", "score": 0.86}],
                        "thresholds": {"match": 0.7, "possible": 0.45},
                        "margin": 0.21,
                    },
                    "review_status": "UNREVIEWED",
                    "effective_asset_type": None,
                    "effective_condition": None,
                    "effective_severity": None,
                    "created_at": "2026-11-15T12:02:31Z",
                    "image_url": "http://localhost:9000/mgts-infra/frames/b2c3d4e5/frame_000007.jpg"
                    "?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Expires=3600",
                    "crop_url": None,
                }
            ]
        },
    )

    id: uuid.UUID = Field(description="Идентификатор наблюдения (UUID)")
    asset_id: uuid.UUID | None = Field(
        description="Связанный актив; null до разрешения дедупликации (POSSIBLE_MATCH/AMBIGUOUS)"
    )
    processing_job_id: uuid.UUID = Field(
        description="Job, создавший наблюдение (фильтр запроса называется job_id)"
    )
    frame_id: str | None = Field(description="Идентификатор кадра", examples=["frame_000007"])
    detection_id: uuid.UUID | None = Field(
        description="Уникальный id детекции в ответе ML (идемпотентность повторной обработки)"
    )
    observed_at: datetime = Field(
        description="Время наблюдения (из GPS-трека); поле фильтрации date_from/date_to"
    )
    detected_at: datetime = Field(description="Время инференса ML")
    object_type: str = Field(
        description="Исходный тип объекта по ML (не затирается review)", examples=["telecom_well"]
    )
    condition_class: str | None = Field(
        description="Исходный класс состояния по ML", examples=["missing_cover"]
    )
    detector_confidence: float = Field(description="Уверенность детектора 0–1", examples=[0.93])
    classifier_confidence: float | None = Field(
        description="Уверенность классификатора состояния 0–1", examples=[0.88]
    )
    severity: int | None = Field(description="Исходная тяжесть 1–5 по ML", examples=[5])
    bbox: dict[str, Any] | None = Field(
        default=None,
        description="Detection bounding box in absolute pixels of the source image: "
        "{x_min, y_min, x_max, y_max}",
    )
    image_width: int | None = Field(description="Ширина исходного кадра, px", examples=[1920])
    image_height: int | None = Field(description="Высота исходного кадра, px", examples=[1080])
    image_id: uuid.UUID | None = Field(description="StoredFile исходного кадра")
    crop_image_id: uuid.UUID | None = Field(description="StoredFile кропа вокруг bbox")
    longitude: float | None = Field(default=None, description="Долгота (WGS84)")
    latitude: float | None = Field(default=None, description="Широта (WGS84)")
    location_accuracy_m: float | None = Field(description="Точность координат, м")
    geolocation_status: GeolocationStatus = Field(description="Достоверность геопривязки")
    geolocation_source: GeolocationSource = Field(description="Источник координат")
    tracking_id: str | None = Field(
        description="Id трекинга объекта между кадрами одного job", examples=["track-0007"]
    )
    model_name: str | None = Field(description="Имя ML-модели", examples=["mgts-detector"])
    model_version: str | None = Field(description="Версия ML-модели", examples=["1.0.0"])
    dedup_result: DeduplicationResult | None = Field(description="Результат дедупликации")
    dedup_score: float | None = Field(description="Итоговый score совпадения 0–1", examples=[0.86])
    dedup_explanation: dict[str, Any] | None = Field(
        default=None,
        description="Machine-readable deduplication decision explanation "
        "(candidate scores, weights, thresholds, margin)",
    )
    review_status: ObservationReviewStatus = Field(description="Статус операторской проверки")
    effective_asset_type: str | None = Field(
        description="Тип объекта после review (null, если исправлений не было)"
    )
    effective_condition: str | None = Field(description="Состояние после review")
    effective_severity: int | None = Field(description="Тяжесть после review")
    created_at: datetime = Field(description="Дата создания записи")
    image_url: str | None = Field(
        default=None,
        description="Ссылка на кадр (presigned S3 или /api/v1/files/...); null для VIEWER",
    )
    crop_url: str | None = Field(
        default=None, description="Ссылка на кроп детекции; null для VIEWER"
    )


class DefectResponse(BaseModel):
    """Дефект физического объекта. observation_count — число связанных наблюдений."""

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "examples": [
                {
                    "id": "e5f6a7b8-c9d0-4e1f-2a3b-4c5d6e7f8091",
                    "asset_id": "3f2b8c1e-9d4a-4f6b-8e2c-1a5d7b9f0c34",
                    "defect_type": "missing_cover",
                    "description": "Отсутствует крышка кабельного колодца",
                    "severity": 5,
                    "status": "OPEN",
                    "first_detected_at": "2026-11-15T12:00:07Z",
                    "last_detected_at": "2026-11-15T12:00:07Z",
                    "resolved_at": None,
                    "created_at": "2026-11-15T12:02:31Z",
                    "updated_at": "2026-11-15T12:02:31Z",
                    "observation_count": 1,
                }
            ]
        },
    )

    id: uuid.UUID = Field(description="Идентификатор дефекта (UUID)")
    asset_id: uuid.UUID = Field(description="Объект, на котором обнаружен дефект")
    defect_type: str = Field(
        description="Тип дефекта из реестра: missing_cover, damaged_cover, well_subsidence, "
        "cabinet_damage, cabinet_door_open, pole_tilt, pole_damage, cable_break, cable_sag, other",
        examples=["missing_cover"],
    )
    description: str | None = Field(description="Описание дефекта (может задаваться оператором)")
    severity: int = Field(description="Тяжесть 1–5", examples=[5])
    status: DefectStatus = Field(description="Статус (матрица переходов — в PATCH /defects)")
    first_detected_at: datetime = Field(description="Первое обнаружение")
    last_detected_at: datetime = Field(
        description="Последнее обнаружение; поле фильтрации date_from/date_to для /defects"
    )
    resolved_at: datetime | None = Field(
        description="Дата устранения (заполняется при RESOLVED, очищается при reopen)"
    )
    created_at: datetime = Field(description="Дата создания записи")
    updated_at: datetime = Field(description="Дата последнего обновления")
    observation_count: int | None = Field(
        default=None, description="Число наблюдений, подтверждающих дефект", examples=[1]
    )


class DefectPatchRequest(BaseModel):
    """Обновление дефекта (OPERATOR+). Семантика присутствия полей (exclude_unset):
    явный null description очищает описание. Матрица переходов статуса:
    OPEN → CONFIRMED/IN_PROGRESS/RESOLVED/REJECTED; CONFIRMED → IN_PROGRESS/RESOLVED;
    IN_PROGRESS → CONFIRMED/RESOLVED; RESOLVED → OPEN (reopen, очищает resolved_at);
    REJECTED терминален через API (возврат только через review workflow).
    RESOLVED заполняет resolved_at. Недопустимый переход → 422 validation_error."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {"status": "CONFIRMED"},
                {"status": "RESOLVED", "description": "Крышка установлена 16.11.2026"},
                {"severity": 4},
            ]
        }
    )

    status: DefectStatus | None = Field(
        default=None, description="Целевой статус (проверяется по матрице переходов)"
    )
    severity: int | None = Field(default=None, ge=1, le=5, description="Тяжесть 1–5")
    description: str | None = Field(default=None, description="Описание; явный null очищает поле")

    @model_validator(mode="after")
    def _not_empty(self) -> DefectPatchRequest:
        if not self.model_fields_set:
            raise ValueError("At least one field must be provided")
        return self


class ReviewCreateRequest(BaseModel):
    """Операторская проверка (append-only). Цель — observation_id или defect_id
    (хотя бы одно). CORRECTED требует минимум одно исправление corrected_*;
    исправления при других решениях → 422. corrected_condition проверяется по
    словарю condition и алиасам; неизвестные метки → 422. reviewed_at не может
    быть более чем на 5 минут в будущем."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "observation_id": "7c1e9a2b-4d5f-4a8c-9b3e-2f6a8d0c1e57",
                    "decision": "CONFIRMED",
                    "comment": "Крышка действительно отсутствует",
                },
                {
                    "observation_id": "7c1e9a2b-4d5f-4a8c-9b3e-2f6a8d0c1e57",
                    "decision": "CORRECTED",
                    "corrected_condition": "damaged_cover",
                    "corrected_severity": 4,
                    "comment": "Крышка на месте, но треснута",
                    "reviewed_at": "2026-11-15T13:00:00Z",
                },
            ]
        }
    )

    observation_id: uuid.UUID | None = Field(
        default=None, description="Проверяемое наблюдение (или defect_id)"
    )
    defect_id: uuid.UUID | None = Field(
        default=None, description="Проверяемый дефект (или observation_id)"
    )
    decision: ReviewDecision = Field(
        description="CONFIRMED / REJECTED / CORRECTED / NEEDS_MORE_INFORMATION"
    )
    corrected_asset_type: str | None = Field(
        default=None,
        max_length=64,
        description="Исправленный тип объекта (только при CORRECTED; из реестра taxonomy)",
        examples=["telecom_cabinet"],
    )
    corrected_condition: str | None = Field(
        default=None,
        max_length=64,
        description="Canonical condition or known alias (ok, damaged, damaged_cover, "
        "missing_cover, door_open, tilted, subsided, cable_sag, cable_break, unknown); "
        "unknown labels are rejected with 422",
        examples=["damaged_cover"],
    )
    corrected_defect_type: str | None = Field(
        default=None,
        max_length=64,
        description="Исправленный тип дефекта (только при CORRECTED; из реестра taxonomy)",
        examples=["damaged_cover"],
    )
    corrected_severity: int | None = Field(
        default=None, ge=1, le=5, description="Исправленная тяжесть 1–5 (только при CORRECTED)"
    )
    comment: str | None = Field(default=None, max_length=4000, description="Комментарий оператора")
    reviewed_at: datetime | None = Field(
        default=None,
        description="Время проверки (ISO 8601); по умолчанию now(UTC); "
        "не более 5 минут в будущем, naive трактуется как UTC",
    )

    @model_validator(mode="after")
    def _target(self) -> ReviewCreateRequest:
        if self.observation_id is None and self.defect_id is None:
            raise ValueError("observation_id or defect_id is required")
        return self


class ReviewResponse(BaseModel):
    """Запись операторской проверки (append-only: не изменяется и не удаляется)."""

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "examples": [
                {
                    "id": "c3d4e5f6-a7b8-4c9d-0e1f-2a3b4c5d6e7f",
                    "observation_id": "7c1e9a2b-4d5f-4a8c-9b3e-2f6a8d0c1e57",
                    "defect_id": None,
                    "reviewer_id": "f6a7b8c9-d0e1-4f2a-3b4c-5d6e7f809102",
                    "decision": "CONFIRMED",
                    "corrected_asset_type": None,
                    "corrected_condition": None,
                    "corrected_defect_type": None,
                    "corrected_severity": None,
                    "comment": "Крышка действительно отсутствует",
                    "reviewed_at": "2026-11-15T13:00:00Z",
                    "created_at": "2026-11-15T13:00:01Z",
                }
            ]
        },
    )

    id: uuid.UUID = Field(description="Идентификатор review (UUID)")
    observation_id: uuid.UUID | None = Field(description="Проверенное наблюдение")
    defect_id: uuid.UUID | None = Field(description="Проверенный дефект")
    reviewer_id: uuid.UUID = Field(description="Кто выполнил проверку")
    decision: ReviewDecision = Field(description="Решение оператора")
    corrected_asset_type: str | None = Field(description="Исправленный тип объекта")
    corrected_condition: str | None = Field(description="Исправленное состояние")
    corrected_defect_type: str | None = Field(description="Исправленный тип дефекта")
    corrected_severity: int | None = Field(description="Исправленная тяжесть")
    comment: str | None = Field(description="Комментарий оператора")
    reviewed_at: datetime = Field(
        description="Время проверки; поле фильтрации date_from/date_to для /reviews"
    )
    created_at: datetime = Field(description="Дата создания записи")


class ConditionHistoryResponse(BaseModel):
    """Запись истории изменения состояния актива (append-only)."""

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "examples": [
                {
                    "id": "2c3d4e5f-6a7b-4c8d-9e0f-1a2b3c4d5e6f",
                    "asset_id": "3f2b8c1e-9d4a-4f6b-8e2c-1a5d7b9f0c34",
                    "observation_id": "7c1e9a2b-4d5f-4a8c-9b3e-2f6a8d0c1e57",
                    "review_id": None,
                    "change_source": "ML_PREDICTION",
                    "previous_condition": "ok",
                    "new_condition": "missing_cover",
                    "previous_severity": 1,
                    "new_severity": 5,
                    "previous_priority": 12.0,
                    "new_priority": 87.5,
                    "is_physical_change": True,
                    "note": None,
                    "detected_at": "2026-11-15T12:00:07Z",
                }
            ]
        },
    )

    id: uuid.UUID = Field(description="Идентификатор записи истории")
    asset_id: uuid.UUID = Field(description="Актив, чьё состояние изменилось")
    observation_id: uuid.UUID | None = Field(description="Наблюдение-инициатор (если есть)")
    review_id: uuid.UUID | None = Field(description="Review-инициатор (если есть)")
    change_source: ConditionChangeSource = Field(
        description="Источник изменения: ML_PREDICTION / HUMAN_REVIEW / MANUAL_EDIT / SYSTEM"
    )
    previous_condition: str | None = Field(description="Предыдущее состояние")
    new_condition: str | None = Field(description="Новое состояние")
    previous_severity: int | None = Field(description="Предыдущая тяжесть")
    new_severity: int | None = Field(description="Новая тяжесть")
    previous_priority: float | None = Field(description="Предыдущий приоритет")
    new_priority: float | None = Field(description="Новый приоритет")
    is_physical_change: bool = Field(
        description="true — зафиксировано физическое изменение объекта (не пересчёт политики)"
    )
    note: str | None = Field(description="Примечание")
    detected_at: datetime = Field(description="Время изменения")


class NearbyAsset(BaseModel):
    """Ближайший актив (PostGIS geography)."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "id": "3f2b8c1e-9d4a-4f6b-8e2c-1a5d7b9f0c34",
                    "asset_type": "telecom_well",
                    "display_name": "Колодец у дома 12 по ул. Тверская",
                    "distance_m": 12.4,
                    "current_priority": 87.5,
                }
            ]
        }
    )

    id: str = Field(description="Идентификатор актива (UUID строкой)")
    asset_type: str = Field(description="Тип объекта", examples=["telecom_well"])
    display_name: str | None = Field(description="Отображаемое имя")
    distance_m: float = Field(
        description="Great-circle distance in meters (geography)", examples=[12.4]
    )
    current_priority: float | None = Field(description="Приоритет 0–100", examples=[87.5])


class NearbyAssetsResponse(BaseModel):
    """Ответ /assets/nearby: ближайшие активы в радиусе, отсортированы по расстоянию."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "items": [
                        {
                            "id": "3f2b8c1e-9d4a-4f6b-8e2c-1a5d7b9f0c34",
                            "asset_type": "telecom_well",
                            "display_name": "Колодец у дома 12 по ул. Тверская",
                            "distance_m": 12.4,
                            "current_priority": 87.5,
                        }
                    ],
                    "total": 1,
                }
            ]
        }
    )

    items: list[NearbyAsset] = Field(
        description="Активы, отсортированные по возрастанию distance_m"
    )
    total: int = Field(description="Число найденных активов (≤ limit)", examples=[1])
