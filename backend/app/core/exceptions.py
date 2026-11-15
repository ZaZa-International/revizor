"""Unified application exception hierarchy.

All API errors are rendered by handlers in app.api.errors into a single envelope:
{"error": {"code", "message", "details", "request_id"}}.
"""

from __future__ import annotations

from typing import Any


class AppError(Exception):
    status_code: int = 500
    code: str = "internal_error"

    def __init__(
        self, message: str = "Internal server error", details: list[dict[str, Any]] | None = None
    ) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or []


class NotFoundError(AppError):
    status_code = 404
    code = "not_found"

    def __init__(self, entity: str, entity_id: Any) -> None:
        super().__init__(f"{entity} '{entity_id}' not found")


class ConflictError(AppError):
    status_code = 409
    code = "conflict"


class ValidationAppError(AppError):
    status_code = 422
    code = "validation_error"


class AuthenticationError(AppError):
    status_code = 401
    code = "authentication_failed"


class PermissionDeniedError(AppError):
    status_code = 403
    code = "permission_denied"


class RateLimitError(AppError):
    status_code = 429
    code = "rate_limited"

    def __init__(self, message: str = "Too many requests", retry_after_seconds: int = 60) -> None:
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


class JobStateError(ConflictError):
    code = "invalid_job_state"


class IdempotencyConflictError(ConflictError):
    code = "idempotency_conflict"


class StorageError(AppError):
    status_code = 503
    code = "storage_unavailable"


class StorageObjectNotFoundError(NotFoundError):
    code = "storage_object_not_found"

    def __init__(self, key: str) -> None:
        super().__init__("Storage object", key)


class MLProviderError(AppError):
    status_code = 502
    code = "ml_provider_error"


class MLTimeoutError(MLProviderError):
    status_code = 504
    code = "ml_timeout"


class MLUnavailableError(MLProviderError):
    status_code = 503
    code = "ml_unavailable"


class MLContractError(MLProviderError):
    status_code = 502
    code = "ml_contract_violation"


class MLInferenceError(MLProviderError):
    status_code = 502
    code = "ml_inference_failed"
