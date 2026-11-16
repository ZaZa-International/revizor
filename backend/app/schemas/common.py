"""Shared API schema primitives: error envelope, pagination, common params."""
# ruff: noqa: RUF001, RUF002  # русскоязычная документация API: кириллица и тире намеренны (ложные срабатывания)

from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

ItemT = TypeVar("ItemT")


class ErrorDetail(BaseModel):
    """Одна ошибка валидации в поле details единого конверта ошибок."""

    field: str | None = Field(
        default=None,
        description="Путь к невалидному полю, например body.longitude или query.page",
        examples=["body.longitude"],
    )
    message: str = Field(
        description="Человекочитаемое описание ошибки",
        examples=["Input should be less than or equal to 180"],
    )
    type: str | None = Field(
        default=None,
        description="Машинный тип ошибки валидации (less_than_equal, missing, uuid_parsing, ...)",
        examples=["less_than_equal"],
    )


class ErrorBody(BaseModel):
    """Тело ошибки единого формата {"error": {...}} (см. docs/api/errors.md)."""

    code: str = Field(
        description="Машинный код ошибки: not_found, validation_error, authentication_failed, "
        "permission_denied, conflict, invalid_job_state, idempotency_conflict, rate_limited, "
        "storage_unavailable, ml_unavailable, ml_timeout, ml_contract_violation, internal_error",
        examples=["not_found"],
    )
    message: str = Field(
        description="Человекочитаемое сообщение",
        examples=["Asset '3f2b8c1e-9d4a-4f6b-8e2c-1a5d7b9f0c34' not found"],
    )
    details: list[ErrorDetail] = Field(
        default_factory=list,
        description="Детали ошибок валидации; для остальных ошибок — пустой список",
    )
    request_id: str | None = Field(
        default=None,
        description="Идентификатор запроса (совпадает с заголовком x-request-id ответа)",
        examples=["6f1c2a9e-4b7d-4e8a-9c31-2f5d8b7a1e04"],
    )


class ErrorResponse(BaseModel):
    """Единый конверт ошибок API: ВСЕ 4xx/5xx, включая 422, используют эту схему
    (не дефолтный FastAPI HTTPValidationError)."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "error": {
                        "code": "not_found",
                        "message": "Asset '3f2b8c1e-9d4a-4f6b-8e2c-1a5d7b9f0c34' not found",
                        "details": [],
                        "request_id": "6f1c2a9e-4b7d-4e8a-9c31-2f5d8b7a1e04",
                    }
                },
                {
                    "error": {
                        "code": "validation_error",
                        "message": "Request validation failed",
                        "details": [
                            {
                                "field": "body.longitude",
                                "message": "Input should be less than or equal to 180",
                                "type": "less_than_equal",
                            }
                        ],
                        "request_id": "6f1c2a9e-4b7d-4e8a-9c31-2f5d8b7a1e04",
                    }
                },
            ]
        }
    )

    error: ErrorBody


class PageMeta(BaseModel):
    """Метаданные страницы списочного ответа."""

    total: int = Field(description="Всего записей, удовлетворяющих фильтрам", examples=[137])
    page: int = Field(description="Текущая страница (начиная с 1)", examples=[1])
    page_size: int = Field(description="Размер страницы (1–100)", examples=[20])
    pages: int = Field(description="Всего страниц", examples=[7])


class PageResponse(BaseModel, Generic[ItemT]):
    """Envelope пагинации всех списочных endpoints: {items, total, page, page_size, pages}."""

    items: list[ItemT] = Field(description="Элементы текущей страницы")
    total: int = Field(description="Всего записей, удовлетворяющих фильтрам", examples=[137])
    page: int = Field(description="Текущая страница (начиная с 1)", examples=[1])
    page_size: int = Field(description="Размер страницы (1–100)", examples=[20])
    pages: int = Field(description="Всего страниц", examples=[7])


class MessageResponse(BaseModel):
    """Простой ответ-сообщение (например, результат logout)."""

    model_config = ConfigDict(json_schema_extra={"examples": [{"message": "logged out"}]})

    message: str = Field(description="Текст сообщения", examples=["logged out"])
    data: dict[str, Any] | None = Field(default=None, description="Опциональные данные")


def page_dict(items: list[Any], page: Any) -> dict[str, Any]:
    """Pagination envelope for already-serialized items (repo Page -> API dict)."""
    return {
        "items": items,
        "total": page.total,
        "page": page.page,
        "page_size": page.page_size,
        "pages": page.pages,
    }


def page_response(page: Any, item_schema: type[BaseModel]) -> dict[str, Any]:
    return page_dict(
        [item_schema.model_validate(item).model_dump(mode="json") for item in page.items], page
    )
