"""Prometheus metrics registry and application metrics."""

from __future__ import annotations

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram

REGISTRY = CollectorRegistry()

HTTP_REQUESTS = Counter(
    "http_requests_total",
    "HTTP requests",
    ["method", "path_template", "status"],
    registry=REGISTRY,
)
HTTP_LATENCY = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency",
    ["method", "path_template"],
    registry=REGISTRY,
)
FRAMES_PROCESSED = Counter("pipeline_frames_processed_total", "Frames processed", registry=REGISTRY)
FRAMES_REJECTED = Counter(
    "pipeline_frames_rejected_total",
    "Frames rejected by quality gate",
    ["reason"],
    registry=REGISTRY,
)
FRAMES_FAILED = Counter(
    "pipeline_frames_failed_total", "Frames failed during processing", registry=REGISTRY
)
DETECTIONS = Counter("pipeline_detections_total", "ML detections produced", registry=REGISTRY)
DEDUP_RESULTS = Counter(
    "deduplication_results_total", "Deduplication outcomes", ["result"], registry=REGISTRY
)
ML_LATENCY = Histogram(
    "ml_inference_duration_seconds",
    "ML inference latency",
    ["provider", "operation"],
    registry=REGISTRY,
)
ML_ERRORS = Counter(
    "ml_errors_total", "ML provider errors", ["provider", "code"], registry=REGISTRY
)
JOB_DURATION = Histogram(
    "processing_job_duration_seconds", "Processing job duration", ["status"], registry=REGISTRY
)
QUEUE_LENGTH = Gauge("rq_queue_length", "RQ queue length", ["queue"], registry=REGISTRY)
JOBS_ACTIVE = Gauge("processing_jobs_active", "Jobs in PROCESSING state", registry=REGISTRY)
