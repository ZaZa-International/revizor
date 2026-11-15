"""Optional OpenTelemetry tracing. Disabled by default; no collector required for MVP."""

from __future__ import annotations

from typing import Any

from app.config import Settings
from app.core.logging import get_logger

logger = get_logger(__name__)


def setup_observability(app: Any, settings: Settings) -> None:
    if not settings.otel_enabled:
        return
    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
    from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    resource = Resource.create({"service.name": settings.otel_service_name})
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=settings.otel_exporter_otlp_endpoint))
    )
    trace.set_tracer_provider(provider)
    FastAPIInstrumentor.instrument_app(app)
    SQLAlchemyInstrumentor().instrument()
    HTTPXClientInstrumentor().instrument()
    logger.info("otel_enabled", endpoint=settings.otel_exporter_otlp_endpoint)
