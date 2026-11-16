"""Custom APIRoute: единый контракт ошибок в OpenAPI (только документация).

Заменяет дефолтный FastAPI 422 (HTTPValidationError) на существующий
ErrorResponse и декларирует общие ошибки для каждой операции:
401 (protected), 403 (role-restricted), 404 (path ids / files / exports),
409+429 (POST uploads/jobs/reviews/routes), 429 (login), 503 (health).
Runtime-поведение endpoint'ов не меняется: класс влияет только на схему.
"""
# ruff: noqa: RUF001  # русскоязычная документация API: кириллица и тире намеренны (ложные срабатывания)

from __future__ import annotations

from typing import Any

from fastapi.dependencies.models import Dependant
from fastapi.routing import APIRoute
from fastapi.utils import create_model_field, is_body_allowed_for_status_code

from app.schemas.common import ErrorResponse

_REQUEST_ID = "6f1c2a9e-4b7d-4e8a-9c31-2f5d8b7a1e04"


def _envelope(code: str, message: str, details: list[dict[str, Any]] | None = None) -> dict:
    return {
        "error": {
            "code": code,
            "message": message,
            "details": details or [],
            "request_id": _REQUEST_ID,
        }
    }


def _error_response(
    code: str, message: str, description: str, details: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    return {
        "model": ErrorResponse,
        "description": description,
        "content": {"application/json": {"example": _envelope(code, message, details)}},
    }


_ERROR_401 = _error_response(
    "authentication_failed",
    "Missing bearer token",
    "Токен отсутствует, просрочен, отозван (logout) или пользователь неактивен. "
    "Выполните POST /api/v1/auth/login и повторите запрос с заголовком "
    "`Authorization: Bearer <access_token>`.",
)
_ERROR_403 = _error_response(
    "permission_denied",
    "Role VIEWER is not allowed; requires one of ['ADMIN', 'OPERATOR', 'SERVICE']",
    "Роли недостаточно для этой операции (например, VIEWER пытается создать загрузку) "
    "или доступ к медиа/удалению чужого объекта запрещён. См. docs/api/authentication.md.",
)
_ERROR_404 = _error_response(
    "not_found",
    "Asset '3f2b8c1e-9d4a-4f6b-8e2c-1a5d7b9f0c34' not found",
    "Сущность с указанным идентификатором не найдена (или объект хранилища отсутствует).",
)
_ERROR_404_EXPORT = _error_response(
    "not_found",
    "Storage object 'exports/assets-export-20261115.csv' not found",
    "Запрошенный объект выгрузки не найден в хранилище.",
)
_ERROR_409 = _error_response(
    "conflict",
    "Data conflict (unique or foreign key constraint)",
    "Конфликт данных: нарушение уникальности/внешнего ключа, в том числе конкурентное "
    "использование Idempotency-Key (`idempotency_conflict`).",
)
_ERROR_409_JOB_CREATE = _error_response(
    "invalid_job_state",
    "Upload already has an active processing job",
    "У загрузки уже есть активный job (PENDING/QUEUED/PROCESSING) — повторный запуск "
    "запрещён (409 `invalid_job_state`); либо Idempotency-Key использован с другим "
    "payload (409 `idempotency_conflict`).",
)
_ERROR_409_JOB_STATE = _error_response(
    "invalid_job_state",
    "Job in status COMPLETED cannot be retried",
    "Недопустимый переход состояния job. Retry: FAILED/PARTIALLY_COMPLETED/CANCELLED "
    "(и «зависший» PROCESSING); cancel: PENDING/QUEUED/PROCESSING. "
    "См. docs/api/upload-and-processing.md.",
)
_ERROR_409_VERSION = _error_response(
    "conflict",
    "Asset version conflict: expected 3, actual 5",
    "Оптимистичная блокировка: `expected_version` не совпадает с текущей `version` "
    "объекта. Перечитайте asset и повторите PATCH с актуальной версией.",
)
_ERROR_409_DELETE_UPLOAD = _error_response(
    "conflict",
    "Upload has processing jobs and cannot be deleted",
    "У загрузки есть processing jobs — удаление запрещено до их очистки.",
)
_ERROR_429 = _error_response(
    "rate_limited",
    "Too many requests",
    "Превышен лимит частоты запросов (per-user для uploads, per-IP/per-username для "
    "login; шлюз может ограничивать и остальные мутации). Заголовок `Retry-After` "
    "содержит рекомендуемую паузу в секундах.",
)
_ERROR_422 = _error_response(
    "validation_error",
    "Request validation failed",
    "Ошибка валидации запроса (параметры, тело, заголовки). Единый формат ошибок — "
    "ErrorResponse, НЕ FastAPI HTTPValidationError. Поле `details` содержит список "
    "{field, message, type}. См. docs/api/errors.md.",
    details=[
        {
            "field": "body.longitude",
            "message": "Input should be less than or equal to 180",
            "type": "less_than_equal",
        }
    ],
)

_CREATE_POST_PATHS = frozenset({"/uploads", "/jobs", "/reviews", "/routes"})


def _has_role_guard(dependant: Dependant) -> bool:
    for sub in dependant.dependencies:
        if getattr(sub.call, "__qualname__", "").startswith("require_roles."):
            return True
        if _has_role_guard(sub):
            return True
    return False


class DocumentedRoute(APIRoute):
    """APIRoute, дополняющий OpenAPI-декларацию общими ошибками контракта."""

    def __init__(self, path: str, endpoint: Any, **kwargs: Any) -> None:
        super().__init__(path, endpoint, **kwargs)
        for status_code, response in self._shared_error_responses().items():
            if status_code in self.responses or str(status_code) in self.responses:
                continue
            self.responses[status_code] = response
            model = response.get("model")
            if model is not None and is_body_allowed_for_status_code(status_code):
                self.response_fields[status_code] = create_model_field(
                    name=f"Response_{status_code}_{self.unique_id}",
                    type_=model,
                    mode="serialization",
                )

    def _shared_error_responses(self) -> dict[int, dict[str, Any]]:
        path = self.path
        methods = self.methods or set()
        public = path == "/auth/login" or path.startswith("/health")
        additions: dict[int, dict[str, Any]] = {}

        has_inputs = bool(
            self.body_field
            or self.dependant.path_params
            or self.dependant.query_params
            or self.dependant.header_params
            or self.dependant.cookie_params
        )
        if has_inputs:
            additions[422] = _ERROR_422
        if not public:
            additions[401] = _ERROR_401
            if _has_role_guard(self.dependant) or path.startswith("/files"):
                additions[403] = _ERROR_403
            if self.dependant.path_params:
                additions[404] = _ERROR_404
        if path == "/auth/login":
            additions[429] = _ERROR_429
        if "POST" in methods and path in _CREATE_POST_PATHS:
            additions[409] = _ERROR_409_JOB_CREATE if path == "/jobs" else _ERROR_409
            additions[429] = _ERROR_429
        if "POST" in methods and path.startswith("/jobs/") and path.endswith(("/retry", "/cancel")):
            additions[409] = _ERROR_409_JOB_STATE
        if "PATCH" in methods and path.startswith("/assets/"):
            additions[409] = _ERROR_409_VERSION
        if "DELETE" in methods and path.startswith("/uploads/"):
            additions[409] = _ERROR_409_DELETE_UPLOAD
        if path.startswith("/exports"):
            additions[404] = _ERROR_404_EXPORT
        return additions
