"""Password hashing (Argon2id), JWT issuance/validation, RBAC primitives."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from app.core.exceptions import AuthenticationError

_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except VerifyMismatchError:
        return False
    except Exception:
        return False


def create_access_token(
    *, subject: uuid.UUID, role: str, secret: str, algorithm: str, expires_minutes: int
) -> str:
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": str(subject),
        "role": role,
        "iat": now,
        "exp": now + timedelta(minutes=expires_minutes),
        "jti": str(uuid.uuid4()),
        "type": "access",
    }
    return jwt.encode(payload, secret, algorithm=algorithm)


def decode_access_token(token: str, *, secret: str, algorithm: str) -> dict[str, Any]:
    try:
        payload: dict[str, Any] = jwt.decode(
            token, secret, algorithms=[algorithm], options={"require": ["exp", "sub"]}
        )
    except jwt.ExpiredSignatureError as exc:
        raise AuthenticationError("Token expired") from exc
    except jwt.InvalidTokenError as exc:
        raise AuthenticationError("Invalid token") from exc
    if payload.get("type") != "access":
        raise AuthenticationError("Invalid token type")
    return payload
