"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-11-15
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from geoalchemy2 import Geography
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ENUMS: dict[str, tuple[str, ...]] = {
    "user_role": ("ADMIN", "OPERATOR", "VIEWER", "SERVICE"),
    "media_type": ("IMAGE", "VIDEO"),
    "storage_object_kind": ("ORIGINAL", "FRAME", "CROP", "ANONYMIZED", "EXPORT"),
    "anonymization_status": ("NOT_APPLIED", "APPLIED", "FAILED", "SKIPPED"),
    "job_status": (
        "PENDING", "QUEUED", "PROCESSING", "COMPLETED",
        "PARTIALLY_COMPLETED", "FAILED", "CANCELLED",
    ),
    "processing_stage": (
        "VALIDATION", "STORAGE", "FRAME_EXTRACTION", "QUALITY_GATE", "PRIVACY_FILTER",
        "INFERENCE", "NORMALIZATION", "TRACKING", "GEOLOCATION", "DEDUPLICATION",
        "RISK_SCORING", "PERSISTENCE", "COMPLETED",
    ),
    "frame_status": ("PROCESSED", "REJECTED", "FAILED", "SKIPPED"),
    "geolocation_status": ("CONFIRMED", "ESTIMATED", "UNAVAILABLE", "INVALID"),
    "geolocation_source": ("GPS", "MANUAL", "MAP_MATCHING", "VISUAL", "UNKNOWN"),
    "lifecycle_status": ("ACTIVE", "INACTIVE", "RETIRED", "UNKNOWN"),
    "priority_band": ("HIGH_PRIORITY", "MEDIUM_PRIORITY", "LOW_PRIORITY", "NEEDS_REVIEW"),
    "deduplication_result": ("MATCHED", "NEW_ASSET", "POSSIBLE_MATCH", "AMBIGUOUS"),
    "observation_review_status": (
        "UNREVIEWED", "CONFIRMED", "REJECTED", "CORRECTED", "NEEDS_MORE_INFORMATION",
    ),
    "defect_status": ("OPEN", "CONFIRMED", "IN_PROGRESS", "RESOLVED", "REJECTED"),
    "review_decision": ("CONFIRMED", "REJECTED", "CORRECTED", "NEEDS_MORE_INFORMATION"),
    "training_example_status": ("PENDING", "EXPORTED"),
    "condition_change_source": ("ML_PREDICTION", "HUMAN_REVIEW", "MANUAL_EDIT", "SYSTEM"),
}


def enum(name: str) -> postgresql.ENUM:
    return postgresql.ENUM(*ENUMS[name], name=name, create_type=False)


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    bind = op.get_bind()
    for name, values in ENUMS.items():
        postgresql.ENUM(*values, name=name).create(bind, checkfirst=True)

    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("username", sa.String(64), nullable=False),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("role", enum("user_role"), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
        sa.UniqueConstraint("username", name="uq_users_username"),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )
    op.create_index("ix_users_created_at", "users", ["created_at"])

    op.create_table(
        "routes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("vehicle_id", sa.String(64), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("track_geometry", Geography(geometry_type="LINESTRING", srid=4326, spatial_index=False), nullable=True),
        sa.Column("total_distance_m", sa.Float(), nullable=True),
        sa.Column("metadata", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_routes"),
    )
    op.create_index("ix_routes_vehicle_id", "routes", ["vehicle_id"])
    op.create_index("ix_routes_created_at", "routes", ["created_at"])
    op.create_index("ix_routes_track_geometry", "routes", ["track_geometry"], postgresql_using="gist")

    op.create_table(
        "uploads",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("original_filename", sa.String(512), nullable=False),
        sa.Column("storage_key", sa.String(1024), nullable=False),
        sa.Column("content_type", sa.String(128), nullable=False),
        sa.Column("file_size", sa.BigInteger(), nullable=False),
        sa.Column("checksum_sha256", sa.String(64), nullable=False),
        sa.Column("media_type", enum("media_type"), nullable=False),
        sa.Column("uploaded_by", sa.Uuid(), nullable=True),
        sa.Column("route_id", sa.Uuid(), nullable=True),
        sa.Column("metadata", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_uploads"),
        sa.UniqueConstraint("storage_key", name="uq_uploads_storage_key"),
        sa.UniqueConstraint("checksum_sha256", name="uq_uploads_checksum_sha256"),
        sa.ForeignKeyConstraint(["uploaded_by"], ["users.id"], name="fk_uploads_uploaded_by_users", ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["route_id"], ["routes.id"], name="fk_uploads_route_id_routes", ondelete="SET NULL"),
    )
    op.create_index("ix_uploads_uploaded_by", "uploads", ["uploaded_by"])
    op.create_index("ix_uploads_route_id", "uploads", ["route_id"])
    op.create_index("ix_uploads_created_at", "uploads", ["created_at"])

    op.create_table(
        "stored_files",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("storage_key", sa.String(1024), nullable=False),
        sa.Column("kind", enum("storage_object_kind"), nullable=False),
        sa.Column("upload_id", sa.Uuid(), nullable=True),
        sa.Column("content_type", sa.String(128), nullable=False),
        sa.Column("file_size", sa.BigInteger(), nullable=False),
        sa.Column("checksum_sha256", sa.String(64), nullable=True),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("anonymization_status", enum("anonymization_status"), nullable=False),
        sa.Column("metadata", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_stored_files"),
        sa.UniqueConstraint("storage_key", name="uq_stored_files_storage_key"),
        sa.ForeignKeyConstraint(["upload_id"], ["uploads.id"], name="fk_stored_files_upload_id_uploads", ondelete="CASCADE"),
    )
    op.create_index("ix_stored_files_kind", "stored_files", ["kind"])
    op.create_index("ix_stored_files_upload_id", "stored_files", ["upload_id"])
    op.create_index("ix_stored_files_created_at", "stored_files", ["created_at"])

    op.create_table(
        "processing_jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("upload_id", sa.Uuid(), nullable=False),
        sa.Column("route_id", sa.Uuid(), nullable=True),
        sa.Column("status", enum("job_status"), nullable=False),
        sa.Column("progress", sa.Float(), nullable=False),
        sa.Column("current_stage", enum("processing_stage"), nullable=True),
        sa.Column("total_frames", sa.Integer(), nullable=False),
        sa.Column("processed_frames", sa.Integer(), nullable=False),
        sa.Column("failed_frames", sa.Integer(), nullable=False),
        sa.Column("rejected_frames", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("idempotency_key", sa.String(128), nullable=True),
        sa.Column("rq_job_id", sa.String(64), nullable=True),
        sa.Column("options", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_processing_jobs"),
        sa.UniqueConstraint("idempotency_key", name="uq_processing_jobs_idempotency_key"),
        sa.ForeignKeyConstraint(["upload_id"], ["uploads.id"], name="fk_processing_jobs_upload_id_uploads", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["route_id"], ["routes.id"], name="fk_processing_jobs_route_id_routes", ondelete="SET NULL"),
        sa.CheckConstraint("progress >= 0 AND progress <= 1", name="ck_processing_jobs_progress_range"),
        sa.CheckConstraint("total_frames >= 0", name="ck_processing_jobs_total_frames_nonneg"),
        sa.CheckConstraint("processed_frames >= 0", name="ck_processing_jobs_processed_frames_nonneg"),
        sa.CheckConstraint("failed_frames >= 0", name="ck_processing_jobs_failed_frames_nonneg"),
        sa.CheckConstraint("rejected_frames >= 0", name="ck_processing_jobs_rejected_frames_nonneg"),
    )
    op.create_index("ix_processing_jobs_status", "processing_jobs", ["status"])
    op.create_index("ix_processing_jobs_upload_id", "processing_jobs", ["upload_id"])
    op.create_index("ix_processing_jobs_route_id", "processing_jobs", ["route_id"])
    op.create_index("ix_processing_jobs_created_at", "processing_jobs", ["created_at"])

    op.create_table(
        "job_frames",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("frame_index", sa.Integer(), nullable=False),
        sa.Column("stored_file_id", sa.Uuid(), nullable=True),
        sa.Column("status", enum("frame_status"), nullable=False),
        sa.Column("reject_reason", sa.String(128), nullable=True),
        sa.Column("error_code", sa.String(64), nullable=True),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_job_frames"),
        sa.UniqueConstraint("job_id", "frame_index", name="uq_job_frame_index"),
        sa.ForeignKeyConstraint(["job_id"], ["processing_jobs.id"], name="fk_job_frames_job_id_processing_jobs", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["stored_file_id"], ["stored_files.id"], name="fk_job_frames_stored_file_id_stored_files", ondelete="SET NULL"),
    )
    op.create_index("ix_job_frames_job_id", "job_frames", ["job_id"])
    op.create_index("ix_job_frames_status", "job_frames", ["status"])
    op.create_index("ix_job_frames_created_at", "job_frames", ["created_at"])

    op.create_table(
        "assets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("external_id", sa.String(128), nullable=True),
        sa.Column("asset_type", sa.String(64), nullable=False),
        sa.Column("display_name", sa.String(255), nullable=True),
        sa.Column("location", Geography(geometry_type="POINT", srid=4326, spatial_index=False), nullable=True),
        sa.Column("location_accuracy_m", sa.Float(), nullable=True),
        sa.Column("geolocation_status", enum("geolocation_status"), nullable=False),
        sa.Column("current_condition", sa.String(64), nullable=True),
        sa.Column("current_severity", sa.Integer(), nullable=True),
        sa.Column("current_priority", sa.Float(), nullable=True),
        sa.Column("priority_band", enum("priority_band"), nullable=True),
        sa.Column("priority_factors", postgresql.JSONB(), nullable=True),
        sa.Column("priority_policy_version", sa.String(16), nullable=True),
        sa.Column("priority_override", sa.Float(), nullable=True),
        sa.Column("priority_override_reason", sa.Text(), nullable=True),
        sa.Column("lifecycle_status", enum("lifecycle_status"), nullable=False),
        sa.Column("first_observed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_observed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_assets"),
        sa.UniqueConstraint("external_id", name="uq_assets_external_id"),
        sa.CheckConstraint("current_severity IS NULL OR (current_severity >= 1 AND current_severity <= 5)", name="ck_assets_current_severity_range"),
        sa.CheckConstraint("current_priority IS NULL OR (current_priority >= 0 AND current_priority <= 100)", name="ck_assets_current_priority_range"),
        sa.CheckConstraint("priority_override IS NULL OR (priority_override >= 0 AND priority_override <= 100)", name="ck_assets_priority_override_range"),
        sa.CheckConstraint("(location IS NULL) = (geolocation_status IN ('UNAVAILABLE', 'INVALID'))", name="ck_assets_location_matches_status"),
    )
    op.create_index("ix_assets_asset_type", "assets", ["asset_type"])
    op.create_index("ix_assets_geolocation_status", "assets", ["geolocation_status"])
    op.create_index("ix_assets_lifecycle_status", "assets", ["lifecycle_status"])
    op.create_index("ix_assets_current_priority", "assets", ["current_priority"])
    op.create_index("ix_assets_priority_band", "assets", ["priority_band"])
    op.create_index("ix_assets_last_observed_at", "assets", ["last_observed_at"])
    op.create_index("ix_assets_created_at", "assets", ["created_at"])
    op.create_index("ix_assets_location", "assets", ["location"], postgresql_using="gist")

    op.create_table(
        "observations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("asset_id", sa.Uuid(), nullable=True),
        sa.Column("processing_job_id", sa.Uuid(), nullable=False),
        sa.Column("job_frame_id", sa.Uuid(), nullable=True),
        sa.Column("frame_id", sa.String(64), nullable=True),
        sa.Column("detection_id", sa.Uuid(), nullable=True),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("object_type", sa.String(64), nullable=False),
        sa.Column("condition_class", sa.String(64), nullable=True),
        sa.Column("detector_confidence", sa.Float(), nullable=False),
        sa.Column("classifier_confidence", sa.Float(), nullable=True),
        sa.Column("severity", sa.Integer(), nullable=True),
        sa.Column("bbox", postgresql.JSONB(), nullable=True),
        sa.Column("image_width", sa.Integer(), nullable=True),
        sa.Column("image_height", sa.Integer(), nullable=True),
        sa.Column("image_id", sa.Uuid(), nullable=True),
        sa.Column("crop_image_id", sa.Uuid(), nullable=True),
        sa.Column("location", Geography(geometry_type="POINT", srid=4326, spatial_index=False), nullable=True),
        sa.Column("location_accuracy_m", sa.Float(), nullable=True),
        sa.Column("geolocation_status", enum("geolocation_status"), nullable=False),
        sa.Column("geolocation_source", enum("geolocation_source"), nullable=False),
        sa.Column("heading_deg", sa.Float(), nullable=True),
        sa.Column("speed_mps", sa.Float(), nullable=True),
        sa.Column("tracking_id", sa.String(64), nullable=True),
        sa.Column("model_name", sa.String(128), nullable=True),
        sa.Column("model_version", sa.String(64), nullable=True),
        sa.Column("raw_model_payload", postgresql.JSONB(), nullable=True),
        sa.Column("dedup_result", enum("deduplication_result"), nullable=True),
        sa.Column("dedup_score", sa.Float(), nullable=True),
        sa.Column("dedup_explanation", postgresql.JSONB(), nullable=True),
        sa.Column("review_status", enum("observation_review_status"), nullable=False),
        sa.Column("effective_asset_type", sa.String(64), nullable=True),
        sa.Column("effective_condition", sa.String(64), nullable=True),
        sa.Column("effective_severity", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_observations"),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], name="fk_observations_asset_id_assets", ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["processing_job_id"], ["processing_jobs.id"], name="fk_observations_processing_job_id_processing_jobs", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["job_frame_id"], ["job_frames.id"], name="fk_observations_job_frame_id_job_frames", ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["image_id"], ["stored_files.id"], name="fk_observations_image_id_stored_files", ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["crop_image_id"], ["stored_files.id"], name="fk_observations_crop_image_id_stored_files", ondelete="SET NULL"),
        sa.CheckConstraint("detector_confidence >= 0 AND detector_confidence <= 1", name="ck_observations_detector_confidence_range"),
        sa.CheckConstraint("classifier_confidence IS NULL OR (classifier_confidence >= 0 AND classifier_confidence <= 1)", name="ck_observations_classifier_confidence_range"),
        sa.CheckConstraint("severity IS NULL OR (severity >= 1 AND severity <= 5)", name="ck_observations_severity_range"),
        sa.CheckConstraint("(location IS NULL) = (geolocation_status IN ('UNAVAILABLE', 'INVALID'))", name="ck_observations_location_matches_status"),
    )
    op.create_index("ix_observations_asset_id", "observations", ["asset_id"])
    op.create_index("ix_observations_processing_job_id", "observations", ["processing_job_id"])
    op.create_index("ix_observations_observed_at", "observations", ["observed_at"])
    op.create_index("ix_observations_object_type", "observations", ["object_type"])
    op.create_index("ix_observations_geolocation_status", "observations", ["geolocation_status"])
    op.create_index("ix_observations_tracking_id", "observations", ["tracking_id"])
    op.create_index("ix_observations_dedup_result", "observations", ["dedup_result"])
    op.create_index("ix_observations_review_status", "observations", ["review_status"])
    op.create_index("ix_observations_created_at", "observations", ["created_at"])
    op.create_index("ix_observations_location", "observations", ["location"], postgresql_using="gist")
    op.create_index(
        "uq_observations_job_detection",
        "observations",
        ["processing_job_id", "detection_id"],
        unique=True,
        postgresql_where=sa.text("detection_id IS NOT NULL"),
    )

    op.create_table(
        "defects",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("asset_id", sa.Uuid(), nullable=False),
        sa.Column("defect_type", sa.String(64), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("severity", sa.Integer(), nullable=False),
        sa.Column("status", enum("defect_status"), nullable=False),
        sa.Column("first_detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_defects"),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], name="fk_defects_asset_id_assets", ondelete="CASCADE"),
        sa.CheckConstraint("severity >= 1 AND severity <= 5", name="ck_defects_severity_range"),
    )
    op.create_index("ix_defects_asset_id", "defects", ["asset_id"])
    op.create_index("ix_defects_defect_type", "defects", ["defect_type"])
    op.create_index("ix_defects_status", "defects", ["status"])
    op.create_index("ix_defects_last_detected_at", "defects", ["last_detected_at"])
    op.create_index("ix_defects_created_at", "defects", ["created_at"])

    op.create_table(
        "defect_observations",
        sa.Column("defect_id", sa.Uuid(), nullable=False),
        sa.Column("observation_id", sa.Uuid(), nullable=False),
        sa.PrimaryKeyConstraint("defect_id", "observation_id", name="pk_defect_observations"),
        sa.ForeignKeyConstraint(["defect_id"], ["defects.id"], name="fk_defect_observations_defect_id_defects", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["observation_id"], ["observations.id"], name="fk_defect_observations_observation_id_observations", ondelete="CASCADE"),
    )

    op.create_table(
        "reviews",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("observation_id", sa.Uuid(), nullable=True),
        sa.Column("defect_id", sa.Uuid(), nullable=True),
        sa.Column("reviewer_id", sa.Uuid(), nullable=False),
        sa.Column("decision", enum("review_decision"), nullable=False),
        sa.Column("corrected_asset_type", sa.String(64), nullable=True),
        sa.Column("corrected_condition", sa.String(64), nullable=True),
        sa.Column("corrected_defect_type", sa.String(64), nullable=True),
        sa.Column("corrected_severity", sa.Integer(), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_reviews"),
        sa.ForeignKeyConstraint(["observation_id"], ["observations.id"], name="fk_reviews_observation_id_observations", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["defect_id"], ["defects.id"], name="fk_reviews_defect_id_defects", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["reviewer_id"], ["users.id"], name="fk_reviews_reviewer_id_users", ondelete="RESTRICT"),
        sa.CheckConstraint("observation_id IS NOT NULL OR defect_id IS NOT NULL", name="ck_reviews_review_target_present"),
        sa.CheckConstraint("corrected_severity IS NULL OR (corrected_severity >= 1 AND corrected_severity <= 5)", name="ck_reviews_corrected_severity_range"),
    )
    op.create_index("ix_reviews_observation_id", "reviews", ["observation_id"])
    op.create_index("ix_reviews_defect_id", "reviews", ["defect_id"])
    op.create_index("ix_reviews_reviewer_id", "reviews", ["reviewer_id"])
    op.create_index("ix_reviews_reviewed_at", "reviews", ["reviewed_at"])
    op.create_index("ix_reviews_created_at", "reviews", ["created_at"])

    op.create_table(
        "training_examples",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("observation_id", sa.Uuid(), nullable=False),
        sa.Column("review_id", sa.Uuid(), nullable=False),
        sa.Column("image_storage_key", sa.String(1024), nullable=False),
        sa.Column("label", postgresql.JSONB(), nullable=False),
        sa.Column("status", enum("training_example_status"), nullable=False),
        sa.Column("exported_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_training_examples"),
        sa.UniqueConstraint("observation_id", name="uq_training_examples_observation_id"),
        sa.ForeignKeyConstraint(["observation_id"], ["observations.id"], name="fk_training_examples_observation_id_observations", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["review_id"], ["reviews.id"], name="fk_training_examples_review_id_reviews", ondelete="CASCADE"),
    )
    op.create_index("ix_training_examples_status", "training_examples", ["status"])
    op.create_index("ix_training_examples_created_at", "training_examples", ["created_at"])

    op.create_table(
        "asset_condition_history",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("asset_id", sa.Uuid(), nullable=False),
        sa.Column("observation_id", sa.Uuid(), nullable=True),
        sa.Column("review_id", sa.Uuid(), nullable=True),
        sa.Column("change_source", enum("condition_change_source"), nullable=False),
        sa.Column("previous_condition", sa.String(64), nullable=True),
        sa.Column("new_condition", sa.String(64), nullable=True),
        sa.Column("previous_severity", sa.Integer(), nullable=True),
        sa.Column("new_severity", sa.Integer(), nullable=True),
        sa.Column("previous_priority", sa.Float(), nullable=True),
        sa.Column("new_priority", sa.Float(), nullable=True),
        sa.Column("is_physical_change", sa.Boolean(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_asset_condition_history"),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], name="fk_asset_condition_history_asset_id_assets", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["observation_id"], ["observations.id"], name="fk_asset_condition_history_observation_id_observations", ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["review_id"], ["reviews.id"], name="fk_asset_condition_history_review_id_reviews", ondelete="SET NULL"),
    )
    op.create_index("ix_asset_condition_history_asset_id", "asset_condition_history", ["asset_id"])
    op.create_index("ix_asset_condition_history_detected_at", "asset_condition_history", ["detected_at"])
    op.create_index("ix_asset_condition_history_created_at", "asset_condition_history", ["created_at"])

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=True),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("entity_type", sa.String(64), nullable=False),
        sa.Column("entity_id", sa.Uuid(), nullable=True),
        sa.Column("before_state", postgresql.JSONB(), nullable=True),
        sa.Column("after_state", postgresql.JSONB(), nullable=True),
        sa.Column("request_id", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_audit_logs"),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"], name="fk_audit_logs_actor_id_users", ondelete="SET NULL"),
    )
    op.create_index("ix_audit_logs_actor_id", "audit_logs", ["actor_id"])
    op.create_index("ix_audit_logs_created_at", "audit_logs", ["created_at"])
    op.create_index("ix_audit_logs_entity", "audit_logs", ["entity_type", "entity_id"])

    op.create_table(
        "idempotency_keys",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.String(128), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("endpoint", sa.String(128), nullable=False),
        sa.Column("response_status", sa.Integer(), nullable=False),
        sa.Column("response_body", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_idempotency_keys"),
        sa.UniqueConstraint("key", "user_id", "endpoint", name="uq_idempotency_scope"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_idempotency_keys_user_id_users", ondelete="CASCADE"),
    )
    op.create_index("ix_idempotency_keys_created_at", "idempotency_keys", ["created_at"])


def downgrade() -> None:
    for table in (
        "idempotency_keys",
        "audit_logs",
        "asset_condition_history",
        "training_examples",
        "reviews",
        "defect_observations",
        "defects",
        "observations",
        "assets",
        "job_frames",
        "processing_jobs",
        "stored_files",
        "uploads",
        "routes",
        "users",
    ):
        op.drop_table(table)
    bind = op.get_bind()
    for name in ENUMS:
        postgresql.ENUM(name=name).drop(bind, checkfirst=True)
