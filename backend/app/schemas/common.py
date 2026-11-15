"""Shared API schema primitives: error envelope, pagination, common params."""

from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

ItemT = TypeVar("ItemT")


class ErrorDetail(BaseModel):
    field: str | None = None
    message: str
    type: str | None = None


class ErrorBody(BaseModel):
    code: str
    message: str
    details: list[ErrorDetail] = Field(default_factory=list)
    request_id: str | None = None


class ErrorResponse(BaseModel):
    error: ErrorBody


class PageMeta(BaseModel):
    total: int
    page: int
    page_size: int
    pages: int


class PageResponse(BaseModel, Generic[ItemT]):
    items: list[ItemT]
    total: int
    page: int
    page_size: int
    pages: int


class MessageResponse(BaseModel):
    message: str
    data: dict[str, Any] | None = None


def page_response(page: Any, item_schema: type[BaseModel]) -> dict[str, Any]:
    return {
        "items": [item_schema.model_validate(item).model_dump(mode="json") for item in page.items],
        "total": page.total,
        "page": page.page,
        "page_size": page.page_size,
        "pages": page.pages,
    }
