"""Processing pipeline orchestrator.

UPLOAD -> VALIDATION -> STORAGE -> JOB -> FRAME EXTRACTION -> QUALITY GATE ->
PRIVACY FILTER -> INFERENCE -> NORMALIZATION -> TRACKING -> GEOLOCATION ->
DEDUPLICATION -> RISK SCORING -> PERSISTENCE -> COMPLETED

Responsibilities are split: this module orchestrates job lifecycle and frame
flow; FramePersistence owns transactional writes; JobProgressTracker owns
progress/finalization. Per-frame failures do not abort the job; re-runs are
idempotent via job_frames + (job_id, detection_id) uniqueness and write-ahead
ML responses (REL-4). Execution is fenced by a session-level PostgreSQL
advisory lock per job (REL-3): a second concurrent run() skips.
"""

from __future__ import annotations

import shutil
import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path

import cv2
import numpy as np
from app.application.interfaces.ml_provider import MLProvider
from app.application.interfaces.storage import ObjectStorage
from app.application.services.geolocation import GeolocationService
from app.application.use_cases.processing.frames import (
    FrameData,
    extract_frames,
    probe_frame_count,
)
from app.application.use_cases.processing.persistence import (
    FramePersistence,
    crop_storage_key,
)
from app.application.use_cases.processing.privacy import NoopPrivacyFilter, PrivacyFilter
from app.application.use_cases.processing.progress import JobProgressTracker
from app.application.use_cases.processing.quality import HeuristicQualityGate, QualityGate
from app.config import Settings
from app.core import metrics
from app.core.exceptions import AppError, MLProviderError, ValidationAppError
from app.core.logging import get_logger, job_id_var
from app.domain.enums import FrameStatus, JobStatus, ProcessingStage, StorageObjectKind
from app.domain.processing.state_machine import assert_transition
from app.infrastructure.database.models.job import ProcessingJob
from app.infrastructure.database.models.stored_file import StoredFile
from app.infrastructure.database.models.upload import Upload
from app.infrastructure.database.repositories.jobs import JobFrameRepository, JobRepository
from app.infrastructure.database.session import Database
from app.schemas.ml import (
    MLFrameMetadata,
    MLImageRef,
    MLInferenceRequest,
    MLInferenceResponse,
)
from sqlalchemy import text

logger = get_logger(__name__)

__all__ = ["ProcessingPipeline", "crop_storage_key", "frame_request_id"]

_CANCEL_CHECK_EVERY = 10
_PROGRESS_EVERY = 5


def frame_request_id(job_id: uuid.UUID, frame_index: int) -> uuid.UUID:
    """Deterministic ML request id: re-inference of a frame is provider-side
    idempotent and mock providers stay deterministic across re-runs (REL-4)."""
    return uuid.uuid5(uuid.NAMESPACE_URL, f"{job_id}:{frame_index}")


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
        self._persistence = FramePersistence(storage, settings)
        self._progress = JobProgressTracker(database)

    async def run(self, job_id: uuid.UUID) -> None:
        """Fenced execution (REL-3): a session-level advisory lock on a dedicated
        connection is held for the whole run; it auto-releases if the process
        crashes. A concurrent run() that cannot acquire it skips immediately."""
        job_id_var.set(str(job_id))
        lock_key = str(job_id)
        try:
            async with self._database.engine.connect() as lock_conn:
                acquired = (
                    await lock_conn.execute(
                        text("SELECT pg_try_advisory_lock(hashtextextended(:key, 0))"),
                        {"key": lock_key},
                    )
                ).scalar_one()
                if not acquired:
                    logger.info("pipeline_locked_skip", job_id=lock_key)
                    return
                await lock_conn.commit()
                try:
                    await self._run_job(job_id)
                finally:
                    try:
                        await lock_conn.execute(
                            text("SELECT pg_advisory_unlock(hashtextextended(:key, 0))"),
                            {"key": lock_key},
                        )
                        await lock_conn.commit()
                    except Exception:
                        logger.warning("pipeline_lock_release_failed", job_id=lock_key)
        finally:
            job_id_var.set(None)

    async def _run_job(self, job_id: uuid.UUID) -> None:
        self._progress.reset()
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
                if job.status == JobStatus.PENDING:
                    assert_transition(job.status, JobStatus.QUEUED)
                    job.status = JobStatus.QUEUED
                assert_transition(job.status, JobStatus.PROCESSING)
            job.status = JobStatus.PROCESSING
            job.current_stage = ProcessingStage.FRAME_EXTRACTION
            if job.started_at is None:
                job.started_at = started
            upload = await session.get(Upload, job.upload_id)
            if upload is None:
                await self._progress.fail_job(
                    session, job, "upload_missing", "Upload record missing", started
                )
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
                    await self._progress.fail_job(session, job, exc.code, exc.message, started)
                    await session.commit()
                return

            geolocation = GeolocationService.from_metadata(
                metadata, gps_max_accuracy_m=self._settings.gps_max_accuracy_m
            )
            started_at = self._resolve_start(metadata, upload_created)
            total = probe_frame_count(
                local_path,
                media_type,
                self._settings.processing_frame_interval_seconds,
                self._settings.processing_max_frames,
                settings=self._settings,
            )
            async with self._database.session() as session:
                job = await JobRepository(session).get_or_raise(job_id)
                job.total_frames = max(
                    total, job.processed_frames + job.rejected_frames + job.failed_frames
                )
                await session.commit()

            frames = extract_frames(
                local_path,
                media_type,
                started_at=started_at,
                interval_seconds=self._settings.processing_frame_interval_seconds,
                max_frames=self._settings.processing_max_frames,
                settings=self._settings,
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
                total = max(total, frame.index + 1)
                stage_before = self._progress.last_stage
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
                        await self._persistence.record_frame(
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
                stage_changed = self._progress.last_stage != stage_before
                if (
                    (frame.index + 1) % _PROGRESS_EVERY == 0
                    or stage_changed
                    or outcome == FrameStatus.FAILED
                ):
                    await self._progress.update_progress(job_id, total, processed, rejected, failed)

            await self._progress.finalize(job_id, cancelled, started)
        except ValidationAppError as exc:
            async with self._database.session() as session:
                job = await JobRepository(session).get_or_raise(job_id)
                await self._progress.fail_job(session, job, exc.code, exc.message, started)
                await session.commit()
        except Exception as exc:
            logger.exception("pipeline_fatal")
            async with self._database.session() as session:
                job = await JobRepository(session).get_or_raise(job_id)
                await self._progress.fail_job(
                    session, job, "pipeline_error", str(exc)[:500], started
                )
                await session.commit()
        finally:
            shutil.rmtree(workdir, ignore_errors=True)

    def _resolve_start(self, metadata: dict, fallback: datetime) -> datetime:
        raw = metadata.get("capture_started_at")
        if raw:
            try:
                parsed = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
                return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed
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
            cached_payload = existing.ml_response if existing is not None else None

        await self._progress.set_stage(job_id, ProcessingStage.QUALITY_GATE)
        quality = self._quality.evaluate(frame.jpeg_bytes, frame.width, frame.height)
        if quality.verdict.value == "REJECT":
            reason = ",".join(quality.reasons)[:128]
            async with self._database.session() as session:
                await self._persistence.record_frame(
                    session, job_id, frame, FrameStatus.REJECTED, reject_reason=reason
                )
                await session.commit()
            metrics.FRAMES_REJECTED.labels(reason=quality.reasons[0]).inc()
            logger.info("frame_rejected", frame_index=frame.index, reasons=quality.reasons)
            return FrameStatus.REJECTED

        await self._progress.set_stage(job_id, ProcessingStage.PRIVACY_FILTER)
        privacy = await self._privacy.process(frame.jpeg_bytes)
        frame_key = f"frames/{job_id}/{frame.index:06d}.jpg"
        await self._storage.upload(frame_key, privacy.image_bytes, "image/jpeg")

        geo = geolocation.locate(frame.observed_at)
        response: MLInferenceResponse | None = None
        if cached_payload is not None:
            try:
                response = MLInferenceResponse.model_validate(cached_payload)
                logger.info("frame_ml_response_reused", frame_index=frame.index)
            except (ValueError, TypeError):
                logger.warning("frame_ml_response_invalid", frame_index=frame.index)
                response = None
        if response is None:
            request = MLInferenceRequest(
                request_id=frame_request_id(job_id, frame.index),
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
            await self._progress.set_stage(job_id, ProcessingStage.INFERENCE)
            try:
                response = await self._ml.infer_image(request)
            except MLProviderError as exc:
                async with self._database.session() as session:
                    await self._persistence.record_frame(
                        session, job_id, frame, FrameStatus.FAILED, error_code=exc.code
                    )
                    await session.commit()
                logger.warning("frame_ml_error", frame_index=frame.index, code=exc.code)
                return FrameStatus.FAILED
            async with self._database.session() as session:
                await self._persistence.write_ahead_ml_response(
                    session, job_id, frame, response.model_dump(mode="json")
                )
                await session.commit()

        await self._progress.set_stage(job_id, ProcessingStage.PERSISTENCE)
        image: np.ndarray | None = None
        if response.detections:
            image = cv2.imdecode(
                np.frombuffer(privacy.image_bytes, dtype=np.uint8), cv2.IMREAD_COLOR
            )
        async with self._database.session() as session:
            frame_metadata: dict = {"quality": quality.metrics, "frame_index": frame.index}
            if frame.original_width is not None and (
                frame.original_width != frame.width or frame.original_height != frame.height
            ):
                frame_metadata["original_width"] = frame.original_width
                frame_metadata["original_height"] = frame.original_height
            stored_frame = StoredFile(
                storage_key=frame_key,
                kind=StorageObjectKind.FRAME,
                upload_id=upload_id,
                content_type="image/jpeg",
                file_size=len(privacy.image_bytes),
                width=frame.width,
                height=frame.height,
                anonymization_status=privacy.status,
                metadata_=frame_metadata,
            )
            session.add(stored_frame)
            await session.flush()
            frame_row = await self._persistence.ensure_frame_row(session, job_id, frame)
            for ordinal, detection in enumerate(response.detections):
                await self._persistence.persist_detection(
                    session,
                    job_id=job_id,
                    route_id=route_id,
                    frame=frame,
                    stored_frame=stored_frame,
                    job_frame_id=frame_row.id,
                    ordinal=ordinal,
                    image=image,
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
            await self._persistence.record_frame(
                session, job_id, frame, FrameStatus.PROCESSED, stored_file_id=stored_frame.id
            )
            await session.commit()
        return FrameStatus.PROCESSED
