"""Seed synthetic DEMO data for product demonstration.

All data is artificial and explicitly marked demo=True. Coordinates are
synthetic points near Moscow center chosen to form plausible street surveys;
they are NOT real MGTS asset locations.

Run from backend/: uv run python ../scripts/seed_demo.py
Idempotent: skips when demo assets already exist.
"""

from __future__ import annotations

import asyncio
import io
import sys
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

import cv2  # noqa: E402
import numpy as np  # noqa: E402
from geoalchemy2 import WKTElement  # noqa: E402
from sqlalchemy import func, select  # noqa: E402

from app.application.services.history import AssetHistoryService  # noqa: E402
from app.application.services.reviews import ReviewService  # noqa: E402
from app.application.services.risk import RiskScoringService  # noqa: E402
from app.application.services.uploads import UploadService  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.domain.enums import (  # noqa: E402
    ConditionChangeSource,
    DeduplicationResult,
    DefectStatus,
    GeolocationSource,
    GeolocationStatus,
    JobStatus,
    LifecycleStatus,
    MediaType,
    ObservationReviewStatus,
    ProcessingStage,
    ReviewDecision,
    StorageObjectKind,
    UserRole,
)
from app.domain.observations.condition import defect_type_for_condition  # noqa: E402
from app.domain.reviews.logic import ReviewCorrection  # noqa: E402
from app.infrastructure.database.models.asset import Asset  # noqa: E402
from app.infrastructure.database.models.defect import Defect, defect_observations  # noqa: E402
from app.infrastructure.database.models.job import JobFrame, ProcessingJob  # noqa: E402
from app.infrastructure.database.models.observation import Observation  # noqa: E402
from app.infrastructure.database.models.route import Route  # noqa: E402
from app.infrastructure.database.models.stored_file import StoredFile  # noqa: E402
from app.infrastructure.database.models.user import User  # noqa: E402
from app.infrastructure.database.repositories.assets import AssetRepository  # noqa: E402
from app.infrastructure.database.session import Database  # noqa: E402
from app.infrastructure.storage.factory import build_storage  # noqa: E402
from app.infrastructure.storage.s3 import S3Storage  # noqa: E402

SURVEY_1 = datetime(2026, 11, 1, 10, 0, 0, tzinfo=UTC)
SURVEY_2 = datetime(2026, 11, 10, 10, 0, 0, tzinfo=UTC)

ROUTES = [
    ("Demo route A — Tverskaya area", "MGTS-001", 37.6100, 55.7550, 37.6250, 55.7580),
    ("Demo route B — Arbat area", "MGTS-002", 37.5900, 55.7480, 37.6000, 55.7500),
    ("Demo route C — Presnya area", "MGTS-001", 37.5600, 55.7620, 37.5750, 55.7650),
]

ASSET_PLAN = [
    ("telecom_well", "damaged_cover", 4, 0.91, 0),
    ("telecom_well", "missing_cover", 5, 0.88, 0),
    ("telecom_well", "ok", 1, 0.95, 0),
    ("telecom_well", "subsided", 4, 0.72, 0),
    ("telecom_well", "ok", 1, 0.93, 1),
    ("telecom_well", "damaged_cover", 3, 0.62, 1),
    ("pole", "tilted", 4, 0.85, 0),
    ("pole", "ok", 1, 0.96, 0),
    ("pole", "ok", 1, 0.90, 1),
    ("pole", "damaged", 3, 0.58, 2),
    ("telecom_cabinet", "door_open", 3, 0.89, 0),
    ("telecom_cabinet", "damaged", 3, 0.81, 1),
    ("telecom_cabinet", "ok", 1, 0.94, 2),
    ("cable_line", "cable_sag", 3, 0.77, 1),
    ("cable_line", "ok", 1, 0.92, 2),
]


def synthetic_jpeg(seed: int) -> bytes:
    rng = np.random.default_rng(seed)
    image = rng.integers(40, 200, (480, 640, 3), dtype=np.uint8)
    cv2.putText(image, "MGTS DEMO DATA (synthetic)", (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
    for _ in range(8):
        x, y = int(rng.integers(0, 560)), int(rng.integers(60, 400))
        cv2.rectangle(image, (x, y), (x + 70, y + 70), (200, 200, 200), 2)
    ok, buffer = cv2.imencode(".jpg", image)
    assert ok
    return buffer.tobytes()


async def main() -> None:
    settings = get_settings()
    database = Database(settings)
    storage = build_storage(settings)
    if isinstance(storage, S3Storage):
        await storage.ensure_bucket()
    risk = RiskScoringService(settings)

    async with database.session() as session:
        existing = (
            await session.execute(select(func.count(Asset.id)).where(Asset.external_id.like("demo-%")))
        ).scalar_one()
        if existing:
            print("Demo data already present; nothing to do.")
            await database.dispose()
            return

        operator = User(
            username="demo-operator",
            password_hash=hash_password("demo-operator-password"),
            role=UserRole.OPERATOR,
        )
        session.add(operator)
        await session.flush()

        routes: list[Route] = []
        for name, vehicle, lon0, lat0, lon1, lat1 in ROUTES:
            track = [(lon0 + (lon1 - lon0) * i / 9, lat0 + (lat1 - lat0) * i / 9) for i in range(10)]
            coords = ", ".join(f"{lon} {lat}" for lon, lat in track)
            route = Route(
                name=name,
                vehicle_id=vehicle,
                started_at=SURVEY_1,
                finished_at=SURVEY_1 + timedelta(minutes=40),
                track_geometry=WKTElement(f"LINESTRING({coords})", srid=4326),
                metadata_={"demo": True},
            )
            session.add(route)
            await session.flush()
            distance = (
                await session.execute(select(func.ST_Length(Route.track_geometry)).where(Route.id == route.id))
            ).scalar_one()
            route.total_distance_m = float(distance)
            routes.append(route)

        uploads = []
        jobs = []
        for index, route in enumerate(routes):
            jpeg = synthetic_jpeg(index + 1)
            result = await UploadService(session, storage, settings).create_upload(
                stream=io.BytesIO(jpeg),
                filename=f"demo-survey-{index + 1}.jpg",
                content_type="image/jpeg",
                uploaded_by=operator.id,
                route_id=route.id,
                metadata={
                    "demo": True,
                    "capture_started_at": SURVEY_1.isoformat(),
                    "gps_track": [
                        {
                            "timestamp": (SURVEY_1 + timedelta(seconds=i * 40)).isoformat(),
                            "longitude": route_lon(route, i),
                            "latitude": route_lat(route, i),
                            "accuracy_m": 4.0,
                        }
                        for i in range(10)
                    ],
                },
            )
            uploads.append(result.upload)
            job = ProcessingJob(
                upload_id=result.upload.id,
                route_id=route.id,
                status=JobStatus.COMPLETED,
                progress=1.0,
                current_stage=ProcessingStage.COMPLETED,
                total_frames=1,
                processed_frames=1,
                started_at=SURVEY_1,
                finished_at=SURVEY_1 + timedelta(seconds=30),
                options={"demo": True},
            )
            session.add(job)
            await session.flush()
            frame_key = f"frames/{job.id}/000000.jpg"
            await storage.upload(frame_key, jpeg, "image/jpeg")
            frame_file = StoredFile(
                storage_key=frame_key,
                kind=StorageObjectKind.FRAME,
                upload_id=result.upload.id,
                content_type="image/jpeg",
                file_size=len(jpeg),
                width=640,
                height=480,
            )
            session.add(frame_file)
            await session.flush()
            session.add(
                JobFrame(
                    job_id=job.id, frame_index=0, status="PROCESSED",
                    stored_file_id=frame_file.id, observed_at=SURVEY_1,
                )
            )
            jobs.append((job, frame_file))

        assets: list[Asset] = []
        for index, (asset_type, condition, severity, confidence, route_idx) in enumerate(ASSET_PLAN):
            route = routes[route_idx]
            unlocated = index in (3, 9)
            lon = route_lon(route, index % 10) + 0.00004 * (index % 3)
            lat = route_lat(route, index % 10) + 0.00003 * (index % 2)
            asset = Asset(
                external_id=f"demo-{asset_type}-{index + 1:03d}",
                asset_type=asset_type,
                display_name=f"DEMO {asset_type} #{index + 1}",
                location=None if unlocated else WKTElement(f"POINT({lon} {lat})", srid=4326),
                location_accuracy_m=None if unlocated else 4.0,
                geolocation_status=GeolocationStatus.UNAVAILABLE if unlocated else GeolocationStatus.CONFIRMED,
                current_condition=condition,
                current_severity=severity if condition != "ok" else None,
                lifecycle_status=LifecycleStatus.ACTIVE,
                first_observed_at=SURVEY_1,
                last_observed_at=SURVEY_1,
            )
            session.add(asset)
            await session.flush()
            assessment = risk.assess(
                asset_type=asset_type,
                severity=asset.current_severity,
                confidence=confidence,
                review_decision=ReviewDecision.CONFIRMED if index % 3 == 0 else None,
                deduplication_result=DeduplicationResult.NEW_ASSET,
            )
            risk.apply_to_asset(asset, assessment)
            assets.append(asset)

        observations: list[Observation] = []
        for index, (asset_type, condition, severity, confidence, route_idx) in enumerate(ASSET_PLAN):
            asset = assets[index]
            job, frame_file = jobs[route_idx]
            for survey_index, observed_at in enumerate((SURVEY_1, SURVEY_2)):
                if survey_index == 1 and index % 2 == 1:
                    continue
                obs_condition = condition
                obs_severity = severity if condition != "ok" else None
                if index == 0 and survey_index == 1:
                    obs_condition, obs_severity = "missing_cover", 5
                detection_id = uuid.uuid5(uuid.NAMESPACE_URL, f"demo-{index}-{survey_index}")
                observation = Observation(
                    asset_id=asset.id,
                    processing_job_id=job.id,
                    frame_id="frame_000000",
                    detection_id=detection_id if survey_index == 0 else None,
                    observed_at=observed_at + timedelta(seconds=index * 40),
                    detected_at=observed_at + timedelta(seconds=index * 40 + 1),
                    object_type=asset_type,
                    condition_class=obs_condition,
                    detector_confidence=confidence,
                    severity=obs_severity,
                    bbox={"x_min": 120, "y_min": 140, "x_max": 380, "y_max": 400},
                    image_width=640,
                    image_height=480,
                    image_id=frame_file.id,
                    location=asset.location,
                    location_accuracy_m=asset.location_accuracy_m,
                    geolocation_status=asset.geolocation_status,
                    geolocation_source=GeolocationSource.GPS if asset.location is not None else GeolocationSource.UNKNOWN,
                    tracking_id=f"demo-track-{index}" if survey_index == 0 else None,
                    model_name="mock-infrastructure-detector",
                    model_version="0.1.0-mock",
                    raw_model_payload={"demo": True, "condition_class": obs_condition},
                    dedup_result=DeduplicationResult.NEW_ASSET if survey_index == 0 else DeduplicationResult.MATCHED,
                    dedup_score=0.0 if survey_index == 0 else 0.9,
                    dedup_explanation={"demo": True, "reason": "seeded"},
                    review_status=ObservationReviewStatus.UNREVIEWED,
                    effective_asset_type=asset_type,
                    effective_condition=obs_condition,
                    effective_severity=obs_severity,
                )
                session.add(observation)
                await session.flush()
                observations.append(observation)
                if survey_index == 1:
                    asset.last_observed_at = observation.observed_at
                    if index == 0:
                        history = AssetHistoryService(session)
                        await history.record_change(
                            asset=asset, new_condition="missing_cover", new_severity=5,
                            new_priority=asset.current_priority,
                            source=ConditionChangeSource.ML_PREDICTION,
                            detected_at=observation.observed_at,
                            observation_id=observation.id,
                            note="demo: condition worsened between surveys",
                        )
                        asset.current_condition = "missing_cover"
                        asset.current_severity = 5

        possible = Observation(
            asset_id=None,
            processing_job_id=jobs[0][0].id,
            observed_at=SURVEY_2 + timedelta(minutes=5),
            detected_at=SURVEY_2 + timedelta(minutes=5, seconds=1),
            object_type="telecom_well",
            condition_class="damaged",
            detector_confidence=0.55,
            severity=3,
            image_id=jobs[0][1].id,
            location=WKTElement("POINT(37.6173 55.7558)", srid=4326),
            geolocation_status=GeolocationStatus.ESTIMATED,
            geolocation_source=GeolocationSource.GPS,
            model_name="mock-infrastructure-detector",
            model_version="0.1.0-mock",
            dedup_result=DeduplicationResult.POSSIBLE_MATCH,
            dedup_score=0.58,
            dedup_explanation={"demo": True, "reason": "possible match, not merged", "candidate_asset_id": str(assets[0].id)},
            review_status=ObservationReviewStatus.UNREVIEWED,
            effective_asset_type="telecom_well",
            effective_condition="damaged",
            effective_severity=3,
        )
        session.add(possible)
        observations.append(possible)

        defects: list[Defect] = []
        for index, asset in enumerate(assets):
            defect_type = defect_type_for_condition(asset.current_condition or "unknown")
            if defect_type is None:
                continue
            related = [o for o in observations if o.asset_id == asset.id]
            defect = Defect(
                asset_id=asset.id,
                defect_type=defect_type,
                description=f"DEMO defect: {defect_type}",
                severity=asset.current_severity or 3,
                status=DefectStatus.OPEN,
                first_detected_at=SURVEY_1,
                last_detected_at=max(o.observed_at for o in related),
            )
            session.add(defect)
            await session.flush()
            for observation in related:
                await session.execute(
                    defect_observations.insert().values(defect_id=defect.id, observation_id=observation.id)
                )
            defects.append(defect)

        await session.commit()

        review_service = ReviewService(session, risk, AssetHistoryService(session))
        review_plan = [
            (0, ReviewDecision.CONFIRMED, ReviewCorrection(), "Confirmed on site"),
            (1, ReviewDecision.CONFIRMED, ReviewCorrection(), None),
            (4, ReviewDecision.CORRECTED, ReviewCorrection(corrected_severity=2, corrected_condition="damaged"), "Minor damage, not subsidence"),
            (7, ReviewDecision.REJECTED, ReviewCorrection(), "False positive: shadow, not tilt"),
            (10, ReviewDecision.NEEDS_MORE_INFORMATION, ReviewCorrection(), "Need closer photo"),
        ]
        for asset_index, decision, correction, comment in review_plan:
            target = next(o for o in observations if o.asset_id == assets[asset_index].id)
            await review_service.create_review(
                observation_id=target.id,
                defect_id=None,
                reviewer_id=operator.id,
                decision=decision,
                correction=correction,
                comment=comment,
                reviewed_at=SURVEY_2 + timedelta(hours=2),
            )
        await session.commit()

        print("Demo data seeded (ALL SYNTHETIC, marked demo=True):")
        print(f"  routes:       {len(routes)}")
        print(f"  uploads:      {len(uploads)}")
        print(f"  jobs:         {len(jobs)} (COMPLETED)")
        print(f"  assets:       {len(assets)} (2 without geolocation)")
        print(f"  observations: {len(observations)} (repeat surveys + 1 POSSIBLE_MATCH)")
        print(f"  defects:      {len(defects)}")
        print("  reviews:      5 (confirmed/corrected/rejected/needs-info)")
        print("  demo operator: demo-operator / demo-operator-password (dev only)")
        print("\nDemo scenario: login -> map/assets -> filter HIGH_PRIORITY ->")
        print("asset history (well #1 worsened) -> review queue -> exports -> analytics/coverage")

    await storage.close()
    await database.dispose()


ROUTE_COORDS = {name: (lon0, lat0, lon1, lat1) for name, _, lon0, lat0, lon1, lat1 in ROUTES}


def route_lon(route: Route, i: int) -> float:
    lon0, _, lon1, _ = ROUTE_COORDS[route.name]
    return round(lon0 + (lon1 - lon0) * i / 9, 7)


def route_lat(route: Route, i: int) -> float:
    _, lat0, _, lat1 = ROUTE_COORDS[route.name]
    return round(lat0 + (lat1 - lat0) * i / 9, 7)


if __name__ == "__main__":
    asyncio.run(main())
