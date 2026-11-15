"""Structured logging with structlog and correlation context."""

from __future__ import annotations

import logging
import sys
from contextvars import ContextVar
from typing import Any

import structlog

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)
job_id_var: ContextVar[str | None] = ContextVar("job_id", default=None)
actor_id_var: ContextVar[str | None] = ContextVar("actor_id", default=None)

_REDACTED_KEYS = {"password", "password_hash", "token", "access_token", "authorization", "secret"}


def _redact_processor(_logger: Any, _method: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    for key in list(event_dict):
        if key.lower() in _REDACTED_KEYS:
            event_dict[key] = "[REDACTED]"
    return event_dict


def _context_processor(_logger: Any, _method: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    for name, var in (
        ("request_id", request_id_var),
        ("job_id", job_id_var),
        ("actor_id", actor_id_var),
    ):
        value = var.get()
        if value is not None:
            event_dict.setdefault(name, value)
    return event_dict


def configure_logging(level: str = "INFO", fmt: str = "json") -> None:
    timestamper = structlog.processors.TimeStamper(fmt="iso", utc=True)
    shared: list[Any] = [
        structlog.contextvars.merge_contextvars,
        _context_processor,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        timestamper,
        _redact_processor,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
        structlog.processors.format_exc_info,
    ]
    renderer: Any = (
        structlog.processors.JSONRenderer()
        if fmt == "json"
        else structlog.dev.ConsoleRenderer(
            colors=False, exception_formatter=structlog.dev.plain_traceback
        )
    )
    structlog.configure(
        processors=[*shared, structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[structlog.stdlib.ProcessorFormatter.remove_processors_meta, renderer],
        foreign_pre_chain=shared,
    )
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level.upper())
    for noisy in ("uvicorn.access", "botocore", "urllib3", "rq"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)
