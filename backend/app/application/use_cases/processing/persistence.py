"""Frame/detection persistence (extracted from the pipeline orchestrator).

Owns the per-frame transactional writes: write-ahead ML responses (REL-4),
detection normalization, geo-cell locking (REL-5), dedup-driven asset
resolution, crops, defects, asset state updates and frame records.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import cv2
import numpy as np
from app.application.interfaces.storage import ObjectStorage
from app.application.services.deduplication import DeduplicationService
from app.application.services.history import AssetHistoryService
from app.application.services.risk import RiskScoringService
from app.application.use_cases.processing.frames import FrameData
from app.config import Settings
from app.core.logging import get_logger
from app.domain.enums import (
    AnonymizationStatus,
    DeduplicationResult,
    FrameStatus,
    GeolocationStatus,
    StorageObjectKind,
)
from app.domain.geospatial.models import GeoObservation, PixelBBox
from app.domain.observations.condition import (
    default_severity_for_condition,
    defect_type_for_condition,
    normalize_condition,
)
from app.infrastructure.database.models.asset import Asset
from app.infrastructure.database.models.defect import Defect
from app.infrastructure.database.models.job import JobFrame
from app.infrastructure.database.models.observation import Observation
from app.infrastructure.database.models.stored_file import StoredFile
from app.infrastructure.database.repositories.assets import AssetRepository, point_element
from app.infrastructure.database.repositories.defects import DefectRepository
from app.infrastructure.database.repositories.jobs import JobFrameRepository
from app.infrastructure.database.repositories.observations import ObservationRepository
from app.schemas.ml import MLBBox
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = get_logger(__name__)


def crop_storage_key(job_id: uuid.UUID, frame_index: int, ordinal: int) -> str:
    """Deterministic crop key (REL-12): re-runs overwrite instead of orphaning."""
    return f"crops/{job_id}/{frame_index:06d}_{ordinal:02d}.jpg"


class FramePersistence:
    def __init__(self, storage: ObjectStorage, settings: Settings) -> None:
        self._storage = storage
        self._settings = settings
        self._risk = RiskScoringService(settings)

    async def write_ahead_ml_response(
        self, session: AsyncSession, job_id: uuid.UUID, frame: FrameData, payload: dict
    ) -> None:
        """Persist the raw ML response BEFORE observation persistence (REL-4).

        A crash after this commit never re-invokes ML for the frame: the re-run
        reuses the stored response. Existing frame status is never touched here.
        """
        repo = JobFrameRepository(session)
        existing = await repo.get_by_index(job_id, frame.index)
        if existing is None:
            session.add(
                JobFrame(
                    job_id=job_id,
                    frame_index=frame.index,
                    status=FrameStatus.FAILED,
                    observed_at=frame.observed_at,
                    ml_response=payload,
                )
            )
        else:
            existing.ml_response = payload
        await session.flush()

    async def ensure_frame_row(
        self, session: AsyncSession, job_id: uuid.UUID, frame: FrameData
    ) -> JobFrame:
        repo = JobFrameRepository(session)
        row = await repo.get_by_index(job_id, frame.index)
        if row is None:
            row = JobFrame(
                job_id=job_id,
                frame_index=frame.index,
                status=FrameStatus.FAILED,
                observed_at=frame.observed_at,
            )
            session.add(row)
            await session.flush()
        return row

    async def persist_detection(
        self,
        session: AsyncSession,
        *,
        job_id: uuid.UUID,
        route_id: uuid.UUID | None,
        frame: FrameData,
        stored_frame: StoredFile,
        job_frame_id: uuid.UUID,
        ordinal: int,
        image: np.ndarray | None,
        detection_payload: dict,
        detection_id: uuid.UUID,
        object_type: str,
        condition_raw: str | None,
        confidence: float,
        severity: int | None,
        bbox: MLBBox,
        embedding: list[float] | None,
        tracking_id: str | None,
        model_name: str,
        model_version: str,
        geo: GeoObservation,
    ) -> None:
        observations = ObservationRepository(session)
        if await observations.exists_by_job_detection(job_id, detection_id):
            logger.info("detection_skipped_duplicate", detection_id=str(detection_id))
            return
        pixel_bbox = PixelBBox(bbox.x_min, bbox.y_min, bbox.x_max, bbox.y_max)
        pixel_bbox.validate(frame.width, frame.height)
        condition = normalize_condition(condition_raw)
        effective_severity = (
            severity
            if severity is not None
            else (
                default_severity_for_condition(condition)
                if condition not in ("ok", "unknown")
                else None
            )
        )
        if geo.point is not None:
            await self._lock_geo_cell(session, object_type, geo)
        dedup = DeduplicationService(session, self._settings)
        decision = await dedup.match(
            object_type=object_type,
            point=geo.point,
            observed_at=frame.observed_at,
            job_id=job_id,
            route_id=route_id,
            tracking_id=tracking_id,
            embedding=embedding,
        )
        assets = AssetRepository(session)
        asset: Asset | None = None
        if decision.result == DeduplicationResult.MATCHED and decision.asset_id:
            asset = await assets.get(uuid.UUID(decision.asset_id))
        elif decision.result == DeduplicationResult.NEW_ASSET:
            asset = Asset(
                asset_type=object_type,
                location=point_element(geo.point) if geo.point else None,
                location_accuracy_m=geo.accuracy_m,
                geolocation_status=geo.status,
                current_condition=condition,
                current_severity=effective_severity,
                first_observed_at=frame.observed_at,
                last_observed_at=frame.observed_at,
            )
            assets.add(asset)
            await session.flush()

        crop_id = await self._store_crop(session, job_id, frame, ordinal, pixel_bbox, image)
        observation = Observation(
            asset_id=asset.id if asset else None,
            processing_job_id=job_id,
            job_frame_id=job_frame_id,
            frame_id=f"frame_{frame.index:06d}",
            detection_id=detection_id,
            observed_at=frame.observed_at,
            detected_at=datetime.now(UTC),
            object_type=object_type,
            condition_class=condition,
            detector_confidence=confidence,
            severity=effective_severity,
            bbox=pixel_bbox.to_dict(),
            image_width=frame.width,
            image_height=frame.height,
            image_id=stored_frame.id,
            crop_image_id=crop_id,
            location=point_element(geo.point) if geo.point else None,
            location_accuracy_m=geo.accuracy_m,
            geolocation_status=geo.status,
            geolocation_source=geo.source,
            heading_deg=geo.heading_deg,
            speed_mps=geo.speed_mps,
            tracking_id=tracking_id,
            model_name=model_name,
            model_version=model_version,
            raw_model_payload=detection_payload,
            dedup_result=decision.result,
            dedup_score=decision.score,
            dedup_explanation=decision.explanation,
            effective_asset_type=object_type,
            effective_condition=condition,
            effective_severity=effective_severity,
        )
        observations.add(observation)
        await session.flush()

        if asset is not None:
            await self._update_asset_from_observation(
                session, asset, observation, decision.result, confidence
            )
            await self._upsert_defect(session, asset, observation, condition, effective_severity)

    async def _lock_geo_cell(
        self, session: AsyncSession, object_type: str, geo: GeoObservation
    ) -> None:
        """Serialize cross-upload dedup races (REL-5) on a ~1.1km grid cell.

        Transaction-scoped advisory lock around match+insert, released at
        commit. Boundary limitation: two objects straddling adjacent cell
        borders can still race; the cell is a coarse serialization hint, not a
        uniqueness guarantee (dedup policy remains the source of truth).
        """
        assert geo.point is not None
        cell_key = f"{object_type}:{int(geo.point.longitude * 100)}:{int(geo.point.latitude * 100)}"
        await session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"), {"key": cell_key}
        )

    async def _store_crop(
        self,
        session: AsyncSession,
        job_id: uuid.UUID,
        frame: FrameData,
        ordinal: int,
        bbox: PixelBBox,
        image: np.ndarray | None,
    ) -> uuid.UUID | None:
        try:
            if image is None:
                return None
            x0, y0 = int(bbox.x_min), int(bbox.y_min)
            x1, y1 = int(bbox.x_max), int(bbox.y_max)
            crop = image[y0:y1, x0:x1]
            if crop.size == 0:
                return None
            ok, buffer = cv2.imencode(".jpg", crop, [cv2.IMWRITE_JPEG_QUALITY, 90])
            if not ok:
                return None
            key = crop_storage_key(job_id, frame.index, ordinal)
            await self._storage.upload(key, buffer.tobytes(), "image/jpeg")
            stored = StoredFile(
                storage_key=key,
                kind=StorageObjectKind.CROP,
                content_type="image/jpeg",
                file_size=len(buffer.tobytes()),
                width=x1 - x0,
                height=y1 - y0,
                anonymization_status=AnonymizationStatus.NOT_APPLIED,
            )
            session.add(stored)
            await session.flush()
            return stored.id
        except Exception as exc:
            logger.warning("crop_store_failed", error=str(exc))
            return None

    async def _update_asset_from_observation(
        self,
        session: AsyncSession,
        asset: Asset,
        observation: Observation,
        dedup_result: DeduplicationResult,
        confidence: float,
    ) -> None:
        history = AssetHistoryService(session)
        assessment = self._risk.assess(
            asset_type=asset.asset_type,
            severity=observation.effective_severity,
            confidence=confidence,
            deduplication_result=dedup_result,
            manual_override=asset.priority_override,
        )
        await history.record_observation(
            asset=asset, observation=observation, new_priority=assessment.priority
        )
        if asset.first_observed_at is None or observation.observed_at < asset.first_observed_at:
            asset.first_observed_at = observation.observed_at
        if asset.last_observed_at is None or observation.observed_at > asset.last_observed_at:
            asset.last_observed_at = observation.observed_at
        asset.current_condition = observation.effective_condition
        asset.current_severity = observation.effective_severity
        if observation.location is not None and self._location_improves(asset, observation):
            asset.location = observation.location
            asset.location_accuracy_m = observation.location_accuracy_m
            asset.geolocation_status = observation.geolocation_status
        asset.version += 1
        self._risk.apply_to_asset(asset, assessment)

    def _location_improves(self, asset: Asset, observation: Observation) -> bool:
        if asset.location is None:
            return True
        rank = {
            GeolocationStatus.CONFIRMED: 3,
            GeolocationStatus.ESTIMATED: 2,
            GeolocationStatus.UNAVAILABLE: 1,
            GeolocationStatus.INVALID: 0,
        }
        if rank[observation.geolocation_status] > rank[asset.geolocation_status]:
            return True
        if observation.geolocation_status == asset.geolocation_status:
            new_acc = observation.location_accuracy_m
            old_acc = asset.location_accuracy_m
            if new_acc is not None and (old_acc is None or new_acc < old_acc):
                return True
        return False

    async def _upsert_defect(
        self,
        session: AsyncSession,
        asset: Asset,
        observation: Observation,
        condition: str,
        severity: int | None,
    ) -> None:
        defect_type = defect_type_for_condition(condition)
        if defect_type is None or severity is None:
            return
        defects = DefectRepository(session)
        defect = await defects.find_open_by_type(asset.id, defect_type)
        if defect is None:
            defect = Defect(
                asset_id=asset.id,
                defect_type=defect_type,
                severity=severity,
                first_detected_at=observation.observed_at,
                last_detected_at=observation.observed_at,
            )
            defects.add(defect)
            await session.flush()
        else:
            defect.last_detected_at = max(defect.last_detected_at, observation.observed_at)
            defect.severity = max(defect.severity, severity)
        await defects.link_observation(defect, observation.id)

    async def record_frame(
        self,
        session: AsyncSession,
        job_id: uuid.UUID,
        frame: FrameData,
        status: FrameStatus,
        *,
        reject_reason: str | None = None,
        error_code: str | None = None,
        stored_file_id: uuid.UUID | None = None,
    ) -> None:
        repo = JobFrameRepository(session)
        existing = await repo.get_by_index(job_id, frame.index)
        if existing is None:
            session.add(
                JobFrame(
                    job_id=job_id,
                    frame_index=frame.index,
                    status=status,
                    reject_reason=reject_reason,
                    error_code=error_code,
                    stored_file_id=stored_file_id,
                    observed_at=frame.observed_at,
                )
            )
        else:
            if existing.status == FrameStatus.PROCESSED and status == FrameStatus.FAILED:
                return
            existing.status = status
            existing.reject_reason = reject_reason
            existing.error_code = error_code
            if stored_file_id is not None:
                existing.stored_file_id = stored_file_id
        await session.flush()
