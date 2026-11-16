"""Application settings loaded from environment variables / .env file."""

from __future__ import annotations

import secrets
from functools import lru_cache
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", case_sensitive=False
    )

    app_env: Literal["development", "production", "test"] = "development"
    app_name: str = "mgts-infra"
    app_version: str = "0.1.0"
    debug: bool = False
    api_v1_prefix: str = "/api/v1"

    database_url: str = "postgresql+asyncpg://mgts:mgts@localhost:5432/mgts_infra"
    database_pool_size: int = 10
    database_max_overflow: int = 20
    database_echo: bool = False

    redis_url: str = "redis://localhost:6379/0"
    queue_mode: Literal["rq", "inline"] = "rq"
    rq_queue_name: str = "processing"
    rq_job_timeout: int = 1800
    rq_result_ttl: int = 86400
    rq_retry_max: int = 3

    storage_backend: Literal["s3", "local"] = "s3"
    storage_local_path: str = "./var/storage"
    s3_endpoint_url: str = "http://localhost:9000"
    s3_public_endpoint_url: str = ""
    s3_access_key: str = "minioadmin"
    s3_secret_key: str = "minioadmin"
    s3_bucket: str = "mgts-infra"
    s3_region: str = "us-east-1"
    s3_presign_expires_seconds: int = 3600

    ml_provider: Literal["mock", "http"] = "mock"
    ml_http_base_url: str = "http://localhost:8001"
    ml_http_timeout_seconds: float = 30.0
    ml_http_retries: int = 2
    ml_http_backoff_seconds: float = 0.5
    ml_contract_version: str = "1.0"

    jwt_secret_key: str = ""
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 60
    bootstrap_admin_username: str = "admin"
    bootstrap_admin_password: str = ""

    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:3000", "http://localhost:5173"]
    )

    max_upload_size_bytes: int = 2 * 1024 * 1024 * 1024
    allowed_image_mime_types: list[str] = Field(
        default_factory=lambda: ["image/jpeg", "image/png", "image/webp"]
    )
    allowed_video_mime_types: list[str] = Field(
        default_factory=lambda: ["video/mp4", "video/x-msvideo", "video/quicktime", "video/webm"]
    )
    allowed_image_extensions: list[str] = Field(
        default_factory=lambda: [".jpg", ".jpeg", ".png", ".webp"]
    )
    allowed_video_extensions: list[str] = Field(
        default_factory=lambda: [".mp4", ".avi", ".mov", ".webm"]
    )

    rate_limit_login_per_minute: int = 10
    rate_limit_login_per_username_per_minute: int = 20
    rate_limit_upload_per_minute: int = 30

    max_json_body_bytes: int = 2 * 1024 * 1024

    processing_frame_interval_seconds: float = 1.0
    processing_max_frames: int = 2000
    processing_max_image_pixels: int = 64_000_000
    processing_max_frame_side: int = 4096
    processing_hard_max_frame_side: int = 8192
    quality_gate_enabled: bool = True
    quality_blur_threshold: float = 60.0
    quality_min_width: int = 320
    quality_min_height: int = 240
    quality_overexposure_mean: float = 245.0
    quality_underexposure_mean: float = 10.0

    dedup_radius_m: float = 15.0
    dedup_match_threshold: float = 0.70
    dedup_possible_threshold: float = 0.45
    dedup_time_window_hours: float = 2.0
    dedup_max_candidates: int = 50

    gps_max_accuracy_m: float = 50.0

    stale_job_grace_seconds: int = 120
    worker_metrics_port: int = 9100

    risk_policy_version: str = "1.0"
    risk_high_threshold: float = 70.0
    risk_medium_threshold: float = 40.0
    risk_review_confidence_threshold: float = 0.6

    otel_enabled: bool = False
    otel_exporter_otlp_endpoint: str = "http://localhost:4318"
    otel_service_name: str = "mgts-infra-backend"

    log_level: str = "INFO"
    log_format: Literal["json", "console"] = "json"
    metrics_enabled: bool = True

    demo_area_bbox: str = "37.55,55.70,37.70,55.80"
    coverage_grid_cell_m: float = 250.0

    @property
    def stale_job_threshold_seconds(self) -> int:
        return self.rq_job_timeout + self.stale_job_grace_seconds

    @model_validator(mode="after")
    def _validate_secrets(self) -> Settings:
        placeholders = {"change-me-in-production", "change-me-admin", "changeme", "secret"}
        if self.app_env == "production":
            if not self.jwt_secret_key or self.jwt_secret_key in placeholders:
                raise ValueError(
                    "JWT_SECRET_KEY must be set to a strong random value in production "
                    "(generate: openssl rand -hex 32)"
                )
            if len(self.jwt_secret_key) < 32:
                raise ValueError("JWT_SECRET_KEY must be at least 32 characters in production")
            if self.bootstrap_admin_password and (
                self.bootstrap_admin_password in placeholders
                or len(self.bootstrap_admin_password) < 12
            ):
                raise ValueError(
                    "BOOTSTRAP_ADMIN_PASSWORD must be empty (skip bootstrap) or a strong "
                    "value (>=12 chars, not a placeholder) in production"
                )
            if self.s3_access_key == "minioadmin" or self.s3_secret_key == "minioadmin":
                raise ValueError("Default S3 credentials are not allowed in production")
            if self.queue_mode == "inline":
                raise ValueError("QUEUE_MODE=inline is not allowed in production")
        if not self.jwt_secret_key:
            object.__setattr__(self, "jwt_secret_key", secrets.token_urlsafe(48))
        if "*" in self.cors_origins:
            raise ValueError(
                "CORS_ORIGINS must not contain '*' while credentials are allowed; "
                "list explicit origins"
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
