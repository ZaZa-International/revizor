"""hardening: restrict history cascades, active-job guard, idempotency scope,
frame ml write-ahead, composite indexes, drop unused indexes, counters check

Revision ID: 0002_hardening
Revises: 0001_initial
Create Date: 2026-11-16
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_hardening"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_RESTRICT_FKS = [
    ("observations", "processing_job_id", "processing_jobs.id",
     "fk_observations_processing_job_id_processing_jobs"),
    ("reviews", "observation_id", "observations.id", "fk_reviews_observation_id_observations"),
    ("reviews", "defect_id", "defects.id", "fk_reviews_defect_id_defects"),
    ("training_examples", "observation_id", "observations.id",
     "fk_training_examples_observation_id_observations"),
    ("training_examples", "review_id", "reviews.id", "fk_training_examples_review_id_reviews"),
]

_DROP_INDEXES = [
    "ix_job_frames_job_id",
    "ix_users_created_at",
    "ix_stored_files_created_at",
    "ix_job_frames_created_at",
    "ix_idempotency_keys_created_at",
    "ix_audit_logs_created_at",
    "ix_asset_condition_history_created_at",
    "ix_training_examples_created_at",
]

_NEW_INDEXES = [
    ("ix_observations_asset_observed", "observations", ["asset_id", "observed_at"]),
    ("ix_observations_review_observed", "observations", ["review_status", "observed_at"]),
    ("ix_defects_status_severity", "defects", ["status", "severity"]),
    ("ix_defects_asset_type_status", "defects", ["asset_id", "defect_type", "status"]),
    ("ix_assets_type_last_observed", "assets", ["asset_type", "last_observed_at"]),
    ("ix_processing_jobs_status_created", "processing_jobs", ["status", "created_at"]),
    ("ix_defect_observations_observation", "defect_observations", ["observation_id"]),
]


def _set_fk_ondelete(table: str, column: str, referent: str, name: str, ondelete: str) -> None:
    op.drop_constraint(name, table, type_="foreignkey")
    op.create_foreign_key(name, table, referent.split(".")[0], [column], ["id"], ondelete=ondelete)


def upgrade() -> None:
    for table, column, referent, name in _RESTRICT_FKS:
        _set_fk_ondelete(table, column, referent, name, "RESTRICT")

    op.drop_constraint("uq_processing_jobs_idempotency_key", "processing_jobs", type_="unique")
    op.create_index(
        "uq_processing_jobs_idempotency_upload",
        "processing_jobs",
        ["idempotency_key", "upload_id"],
        unique=True,
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
    )
    op.create_index(
        "uq_processing_jobs_active_upload",
        "processing_jobs",
        ["upload_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('PENDING', 'QUEUED', 'PROCESSING')"),
    )

    op.add_column("job_frames", sa.Column("ml_response", postgresql.JSONB(), nullable=True))
    op.add_column("idempotency_keys", sa.Column("request_hash", sa.String(64), nullable=True))

    op.create_check_constraint(
        "ck_processing_jobs_frames_sum",
        "processing_jobs",
        "processed_frames + rejected_frames + failed_frames <= total_frames",
    )

    for name, table, columns in _NEW_INDEXES:
        op.create_index(name, table, columns)

    for name in _DROP_INDEXES:
        op.drop_index(name)


def downgrade() -> None:
    for name in _DROP_INDEXES:
        table = name.removeprefix("ix_").rsplit("_created_at", 1)[0]
        if name == "ix_job_frames_job_id":
            op.create_index(name, "job_frames", ["job_id"])
        else:
            op.create_index(name, table, ["created_at"])

    for name, table, _columns in reversed(_NEW_INDEXES):
        op.drop_index(name, table_name=table)

    op.drop_constraint("ck_processing_jobs_frames_sum", "processing_jobs", type_="check")
    op.drop_column("idempotency_keys", "request_hash")
    op.drop_column("job_frames", "ml_response")

    op.drop_index("uq_processing_jobs_active_upload", table_name="processing_jobs")
    op.drop_index("uq_processing_jobs_idempotency_upload", table_name="processing_jobs")
    op.create_unique_constraint(
        "uq_processing_jobs_idempotency_key", "processing_jobs", ["idempotency_key"]
    )

    for table, column, referent, name in _RESTRICT_FKS:
        _set_fk_ondelete(table, column, referent, name, "CASCADE")
