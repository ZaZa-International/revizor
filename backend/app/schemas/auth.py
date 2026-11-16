from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.domain.enums import UserRole


class LoginRequest(BaseModel):
    """Учётные данные для входа (POST /api/v1/auth/login)."""

    model_config = ConfigDict(
        json_schema_extra={"examples": [{"username": "admin", "password": "strong-password"}]}
    )

    username: str = Field(
        min_length=1, max_length=64, description="Имя пользователя", examples=["admin"]
    )
    password: str = Field(
        min_length=1, max_length=256, description="Пароль", examples=["strong-password"]
    )


class UserResponse(BaseModel):
    """Профиль пользователя (текущий или в составе TokenResponse)."""

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "examples": [
                {
                    "id": "f6a7b8c9-d0e1-4f2a-3b4c-5d6e7f809102",
                    "username": "admin",
                    "email": None,
                    "role": "ADMIN",
                    "is_active": True,
                    "created_at": "2026-11-15T09:00:00Z",
                }
            ]
        },
    )

    id: uuid.UUID = Field(description="Идентификатор пользователя (UUID)")
    username: str = Field(description="Имя пользователя", examples=["admin"])
    email: str | None = Field(description="Email (опционально)")
    role: UserRole = Field(description="Роль RBAC: ADMIN, OPERATOR, VIEWER или SERVICE")
    is_active: bool = Field(description="Активен ли пользователь; неактивные не могут входить")
    created_at: datetime = Field(description="Дата создания (ISO 8601, UTC)")


class TokenResponse(BaseModel):
    """Ответ успешного входа: JWT и профиль пользователя."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
                    "eyJzdWIiOiJmNmE3YjhjOS1kMGUxLTRmMmEtM2I0Yy01ZDZlN2Y4MDkxMDIifQ."
                    "signature",
                    "token_type": "bearer",
                    "expires_in_minutes": 60,
                    "user": {
                        "id": "f6a7b8c9-d0e1-4f2a-3b4c-5d6e7f809102",
                        "username": "admin",
                        "email": None,
                        "role": "ADMIN",
                        "is_active": True,
                        "created_at": "2026-11-15T09:00:00Z",
                    },
                }
            ]
        }
    )

    access_token: str = Field(description="JWT для заголовка Authorization: Bearer <access_token>")
    token_type: str = Field(default="bearer", description="Тип токена — всегда bearer")
    expires_in_minutes: int = Field(
        description="Срок жизни токена в минутах (по умолчанию 60)", examples=[60]
    )
    user: UserResponse = Field(description="Профиль вошедшего пользователя")
