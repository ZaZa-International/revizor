"""Processing pipeline orchestrator.

UPLOAD -> VALIDATION -> STORAGE -> JOB -> FRAME EXTRACTION -> QUALITY GATE ->
PRIVACY FILTER -> INFERENCE -> NORMALIZATION -> TRACKING -> GEOLOCATION ->
DEDUPLICATION -> RISK SCORING -> PERSISTENCE -> COMPLETED

Each stage is a separate responsibility. Per-frame failures do not abort the
job; re-runs are idempotent via job_frames + (job_id, detection_id) uniqueness.
"""

from __future__ import annotations

import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path

from app.application.interfaces.ml_provider import MLProvider
from app.application.interfaces.storage import ObjectStorage
from app.application.services.deduplication import DeduplicationService
from app.application.services.geolocation import GeolocationService
from app.application.services.history import AssetHistoryService
from app.application.services.risk import RiskScoringService
from app.application.use_cases.processing.frames import (
    FrameData,
    extract_frames,
    probe_frame_count,
)
from app.application.use_cases.processing.privacy import NoopPrivacyFilter, PrivacyFilter
from app.application.use_cases.processing.quality import HeuristicQualityGate, QualityGate
from app.config import Settings
from app.core import metrics
from app.core.exceptions import AppError, MLProviderError, ValidationAppError
from app.core.logging import get_logger, job_id_var
from app.domain.enums import (
    AnonymizationStatus,
    DeduplicationResult,
    FrameStatus,
    GeolocationStatus,
    JobStatus,
    ProcessingStage,
    StorageObjectKind,
)
from app.domain.geospatial.models import GeoObservation, PixelBBox
from app.domain.observations.condition import (
    default_severity_for_condition,
    defect_type_for_condition,
    normalize_condition,
)
from app.domain.processing.state_machine import assert_transition
from app.infrastructure.database.models.asset import Asset
from app.infrastructure.database.models.defect import Defect
from app.infrastructure.database.models.job import JobFrame, ProcessingJob
from app.infrastructure.database.models.observation import Observation
from app.infrastructure.database.models.stored_file import StoredFile
from app.infrastructure.database.models.upload import Upload
from app.infrastructure.database.repositories.assets import AssetRepository, point_element
from app.infrastructure.database.repositories.defects import DefectRepository
from app.infrastructure.database.repositories.jobs import JobFrameRepository, JobRepository
from app.infrastructure.database.repositories.observations import ObservationRepository
from app.infrastructure.database.session import Database
from app.schemas.ml import MLBBox, MLFrameMetadata, MLImageRef, MLInferenceRequest
from sqlalchemy.ext.asyncio import AsyncSession

logger = get_logger(__name__)

_CANCEL_CHECK_EVERY = 10


class ProcessingPipeline:
    def __init__(
        self,
        database: Database,
        storage: ObjectStorage,
        ml: MLProvider,
        settings: Settings,
        quality_gate: QualityGate | None = None,
        privacy_filter: PrivacyFilter | None = None,
    ) -> None:
        self._database = database
        self._storage = storage
        self._ml = ml
        self._settings = settings
        self._quality = quality_gate or HeuristicQualityGate(settings)
        self._privacy = privacy_filter or NoopPrivacyFilter()
        self._risk = RiskScoringService(settings)
        self._last_stage: ProcessingStage | None = None

    async def _set_stage(self, job_id: uuid.UUID, stage: ProcessingStage) -> None:
        if self._last_stage == stage:
            return
        self._last_stage = stage
        async with self._database.session() as session:
            job = await session.get(ProcessingJob, job_id)
            if job is not None and job.status == JobStatus.PROCESSING:
                job.current_stage = stage
                await session.commit()

    async def run(self, job_id: uuid.UUID) -> None:
        job_id_var.set(str(job_id))
        self._last_stage = None
        started = datetime.now(UTC)
        async with self._database.session() as session:
            jobs = JobRepository(session)
            job = await jobs.get(job_id)
            if job is None:
                logger.error("pipeline_job_missing", job_id=str(job_id))
                return
            if job.status in (JobStatus.COMPLETED, JobStatus.CANCELLED):
                logger.info("pipeline_skip_terminal", status=job.status.value)
                return
            if job.status == JobStatus.PROCESSING:
                logger.warning("pipeline_takeover_processing_job")
            else:
                assert_transition(job.status, JobStatus.PROCESSING)
            job.status = JobStatus.PROCESSING
            job.current_stage = ProcessingStage.FRAME_EXTRACTION
            if job.started_at is None:
                job.started_at = started
            upload = await session.get(Upload, job.upload_id)
            if upload is None:
                await self._fail_job(session, job, "upload_missing", "Upload record missing")
                await session.commit()
                return
            await session.commit()
            upload_id = upload.id
            storage_key = upload.storage_key
            media_type = upload.media_type
            route_id = job.route_id
            metadata = dict(upload.metadata_)
            upload_created = upload.created_at

        workdir = tempfile.mkdtemp(prefix=f"mgts-job-{job_id}-")
        local_path = str(Path(workdir) / "original.bin")
        try:
            try:
                await self._storage.download_to_file(storage_key, local_path)
            except AppError as exc:
                async with self._database.session() as session:
                    job = await JobRepository(session).get_or_raise(job_id)
                    await self._fail_job(session, job, exc.code, exc.message)
                    await session.commit()
                return

            geolocation = GeolocationService.from_metadata(metadata)
            started_at = self._resolve_start(metadata, upload_created)
            total = probe_frame_count(
                local_path,
                media_type,
                self._settings.processing_frame_interval_seconds,
                self._settings.processing_max_frames,
            )
            async with self._database.session() as session:
                job = await JobRepository(session).get_or_raise(job_id)
                job.total_frames = total
                await session.commit()

            frames = extract_frames(
                local_path,
                media_type,
                started_at=started_at,
                interval_seconds=self._settings.processing_frame_interval_seconds,
                max_frames=self._settings.processing_max_frames,
            )
            processed = rejected = failed = 0
            cancelled = False
            for frame in frames:
                if frame.index % _CANCEL_CHECK_EVERY == 0:
                    async with self._database.session() as session:
                        current = await session.get(ProcessingJob, job_id)
                        if current is not None and current.status == JobStatus.CANCELLED:
                            cancelled = True
                            break
                try:
                    outcome = await self._process_frame(
                        job_id=job_id,
                        upload_id=upload_id,
                        route_id=route_id,
                        frame=frame,
                        geolocation=geolocation,
                    )
                except Exception as exc:
                    logger.exception("frame_failed", frame_index=frame.index, error=str(exc))
                    outcome = FrameStatus.FAILED
                    async with self._database.session() as session:
                        await self._record_frame(
                            session,
                            job_id,
                            frame,
                            FrameStatus.FAILED,
                            error_code="frame_processing_error",
                        )
                        await session.commit()
                    metrics.FRAMES_FAILED.inc()
                if outcome == FrameStatus.PROCESSED:
                    processed += 1
                    metrics.FRAMES_PROCESSED.inc()
                elif outcome == FrameStatus.REJECTED:
                    rejected += 1
                elif outcome == FrameStatus.FAILED:
                    failed += 1
                await self._update_progress(job_id, total, processed, rejected, failed)

            await self._finalize(job_id, total, processed, rejected, failed, cancelled, started)
        except ValidationAppError as exc:
            async with self._database.session() as session:
                job = await JobRepository(session).get_or_raise(job_id)
                await self._fail_job(session, job, exc.code, exc.message)
                await session.commit()
        except Exception as exc:
            logger.exception("pipeline_fatal")
            async with self._database.session() as session:
                job = await JobRepository(session).get_or_raise(job_id)
                await self._fail_job(session, job, "pipeline_error", str(exc)[:500])
                await session.commit()
        finally:
            import shutil

            shutil.rmtree(workdir, ignore_errors=True)
            job_id_var.set(None)

    def _resolve_start(self, metadata: dict, fallback: datetime) -> datetime:
        raw = metadata.get("capture_started_at")
        if raw:
            try:
                return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
            except ValueError:
                pass
        return fallback

    async def _process_frame(
        self,
        *,
        job_id: uuid.UUID,
        upload_id: uuid.UUID,
        route_id: uuid.UUID | None,
        frame: FrameData,
        geolocation: GeolocationService,
    ) -> FrameStatus:
        async with self._database.session() as session:
            frames_repo = JobFrameRepository(session)
            existing = await frames_repo.get_by_index(job_id, frame.index)
            if existing is not None and existing.status in (
                FrameStatus.PROCESSED,
                FrameStatus.REJECTED,
                FrameStatus.SKIPPED,
            ):
                return existing.status

        await self._set_stage(job_id, ProcessingStage.QUALITY_GATE)
        quality = self._quality.evaluate(frame.jpeg_bytes, frame.width, frame.height)
        if quality.verdict.value == "REJECT":
            reason = ",".join(quality.reasons)[:128]
            async with self._database.session() as session:
                await self._record_frame(
                    session, job_id, frame, FrameStatus.REJECTED, reject_reason=reason
                )
                await session.commit()
            metrics.FRAMES_REJECTED.labels(reason=quality.reasons[0]).inc()
            logger.info("frame_rejected", frame_index=frame.index, reasons=quality.reasons)
            return FrameStatus.REJECTED

        await self._set_stage(job_id, ProcessingStage.PRIVACY_FILTER)
        privacy = await self._privacy.process(frame.jpeg_bytes)
        frame_key = f"frames/{job_id}/{frame.index:06d}.jpg"
        await self._storage.upload(frame_key, privacy.image_bytes, "image/jpeg")

        geo = geolocation.locate(frame.observed_at)
        request = MLInferenceRequest(
            image=MLImageRef(storage_key=frame_key, width=frame.width, height=frame.height),
            metadata=MLFrameMetadata(
                observed_at=frame.observed_at,
                longitude=geo.point.longitude if geo.point else None,
                latitude=geo.point.latitude if geo.point else None,
                heading_deg=geo.heading_deg,
                speed_mps=geo.speed_mps,
                route_id=str(route_id) if route_id else None,
                frame_index=frame.index,
            ),
        )
        await self._set_stage(job_id, ProcessingStage.INFERENCE)
        try:
            response = await self._ml.infer_image(request)
        except MLProviderError as exc:
            async with self._database.session() as session:
                await self._record_frame(
                    session, job_id, frame, FrameStatus.FAILED, error_code=exc.code
                )
                await session.commit()
            logger.warning("frame_ml_error", frame_index=frame.index, code=exc.code)
            return FrameStatus.FAILED

        await self._set_stage(job_id, ProcessingStage.PERSISTENCE)
        async with self._database.session() as session:
            stored_frame = StoredFile(
                storage_key=frame_key,
                kind=StorageObjectKind.FRAME,
                upload_id=upload_id,
                content_type="image/jpeg",
                file_size=len(privacy.image_bytes),
                width=frame.width,
                height=frame.height,
                anonymization_status=privacy.status,
                metadata_={"quality": quality.metrics, "frame_index": frame.index},
            )
            session.add(stored_frame)
            await session.flush()
            for detection in response.detections:
                await self._persist_detection(
                    session,
                    job_id=job_id,
                    route_id=route_id,
                    frame=frame,
                    stored_frame=stored_frame,
                    detection_payload=detection.model_dump(mode="json"),
                    detection_id=detection.detection_id,
                    object_type=detection.object_type,
                    condition_raw=detection.condition_class,
                    confidence=detection.confidence,
                    severity=detection.severity,
                    bbox=detection.bbox,
                    embedding=detection.embedding,
                    tracking_id=detection.attributes.get("tracking_id"),
                    model_name=response.model.name,
                    model_version=response.model.version,
                    geo=geo,
                )
                metrics.DETECTIONS.inc()
            await self._record_frame(
                session, job_id, frame, FrameStatus.PROCESSED, stored_file_id=stored_frame.id
            )
            await session.commit()
        return FrameStatus.PROCESSED

    async def _persist_detection(
        self,
        session: AsyncSession,
        *,
        job_id: uuid.UUID,
        route_id: uuid.UUID | None,
        frame: FrameData,
        stored_frame: StoredFile,
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

        crop_id = await self._store_crop(session, job_id, frame, detection_id, pixel_bbox)
        observation = Observation(
            asset_id=asset.id if asset else None,
            processing_job_id=job_id,
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

    async def _store_crop(
        self,
        session: AsyncSession,
        job_id: uuid.UUID,
        frame: FrameData,
        detection_id: uuid.UUID,
        bbox: PixelBBox,
    ) -> uuid.UUID | None:
        import cv2
        import numpy as np

        try:
            image = cv2.imdecode(np.frombuffer(frame.jpeg_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
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
            key = f"crops/{job_id}/{detection_id}.jpg"
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

    async def _record_frame(
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
            existing.status = status
            existing.reject_reason = reject_reason
            existing.error_code = error_code
            if stored_file_id is not None:
                existing.stored_file_id = stored_file_id
        await session.flush()

    async def _update_progress(
        self, job_id: uuid.UUID, total: int, processed: int, rejected: int, failed: int
    ) -> None:
        async with self._database.session() as session:
            job = await session.get(ProcessingJob, job_id)
            if job is None or job.status == JobStatus.CANCELLED:
                return
            done = processed + rejected + failed
            job.processed_frames = processed
            job.rejected_frames = rejected
            job.failed_frames = failed
            job.progress = min(1.0, done / total) if total else 0.0
            job.current_stage = ProcessingStage.PERSISTENCE
            await session.commit()

    async def _finalize(
        self,
        job_id: uuid.UUID,
        total: int,
        processed: int,
        rejected: int,
        failed: int,
        cancelled: bool,
        started: datetime,
    ) -> None:
        async with self._database.session() as session:
            job = await JobRepository(session).get_or_raise(job_id)
            frames_repo = JobFrameRepository(session)
            job.processed_frames = await frames_repo.count_by_status(job_id, FrameStatus.PROCESSED)
            job.rejected_frames = await frames_repo.count_by_status(job_id, FrameStatus.REJECTED)
            job.failed_frames = await frames_repo.count_by_status(job_id, FrameStatus.FAILED)
            if cancelled or job.status == JobStatus.CANCELLED:
                job.status = JobStatus.CANCELLED
            elif job.failed_frames == 0:
                job.status = JobStatus.COMPLETED
            elif job.processed_frames > 0 or job.rejected_frames > 0:
                job.status = JobStatus.PARTIALLY_COMPLETED
                job.error_code = "partial_frame_failures"
                job.error_message = f"{job.failed_frames} frame(s) failed"
            else:
                job.status = JobStatus.FAILED
                job.error_code = "all_frames_failed"
                job.error_message = f"All {job.failed_frames} frame(s) failed"
            job.progress = 1.0
            job.current_stage = ProcessingStage.COMPLETED
            job.finished_at = datetime.now(UTC)
            await session.commit()
        duration = (datetime.now(UTC) - started).total_seconds()
        metrics.JOB_DURATION.labels(job.status.value).observe(duration)
        logger.info(
            "pipeline_finished",
            status=job.status.value,
            processed=job.processed_frames,
            rejected=job.rejected_frames,
            failed=job.failed_frames,
            duration_s=round(duration, 2),
        )

    async def _fail_job(
        self, session: AsyncSession, job: ProcessingJob, code: str, message: str
    ) -> None:
        job.status = JobStatus.FAILED
        job.error_code = code
        job.error_message = message[:1000]
        job.finished_at = datetime.now(UTC)
        job.progress = 1.0
        logger.error("pipeline_job_failed", code=code, message=message)
