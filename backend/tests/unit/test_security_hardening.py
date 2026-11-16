"""Wave-1 security hardening regressions (SEC-1/2/7/8/12/13/15/17/19, ARCH-14/28)."""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest
from app.application.services import auth as auth_service_module
from app.application.services.auth import AuthService
from app.application.services.uploads import UploadService, sniff_media_type
from app.config import Settings
from app.core import metrics
from app.core.exceptions import AuthenticationError, PermissionDeniedError, RateLimitError
from app.core.middleware import (
    BodyLimitMiddleware,
    RequestContextMiddleware,
    SecurityHeadersMiddleware,
)
from app.core.ratelimit import RateLimiter
from app.core.security import DUMMY_PASSWORD_HASH
from app.dependencies import can_access_media
from app.domain.enums import MediaType, UserRole
from app.infrastructure.database.models.upload import Upload
from app.infrastructure.database.models.user import User
from app.infrastructure.database.repositories.uploads import UploadRepository
from redis.exceptions import RedisError
from starlette.types import Message, Receive, Scope, Send

pytestmark = pytest.mark.unit

_MB = 1024 * 1024


def _settings(**overrides: Any) -> Settings:
    return Settings(_env_file=None, **overrides)


def _scope(
    path: str = "/api/v1/uploads", method: str = "POST", headers: dict | None = None
) -> Scope:
    return {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "root_path": "",
        "headers": [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()],
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
        "state": {},
    }


class _SendCollector:
    def __init__(self) -> None:
        self.messages: list[Message] = []

    async def __call__(self, message: Message) -> None:
        self.messages.append(message)

    @property
    def status(self) -> int:
        return next(m["status"] for m in self.messages if m["type"] == "http.response.start")

    @property
    def body(self) -> bytes:
        return b"".join(
            m.get("body", b"") for m in self.messages if m["type"] == "http.response.body"
        )

    def header(self, name: str) -> str | None:
        start = next(m for m in self.messages if m["type"] == "http.response.start")
        for key, value in start.get("headers", []):
            if key.decode().lower() == name.lower():
                return value.decode()
        return None


def _echo_app() -> Any:
    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        while True:
            message = await receive()
            if message["type"] != "http.request":
                break
            if not message.get("more_body", False):
                break
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    return app


def _chunked_receive(chunks: list[bytes], calls: list[int] | None = None) -> Receive:
    iterator = iter(chunks)

    async def receive() -> Message:
        if calls is not None:
            calls.append(1)
        chunk = next(iterator, None)
        if chunk is None:
            return {"type": "http.disconnect"}
        return {"type": "http.request", "body": chunk, "more_body": True}

    return receive


async def _disconnect_receive() -> Message:
    return {"type": "http.disconnect"}


def _assert_payload_too_large(collector: _SendCollector) -> None:
    assert collector.status == 413
    envelope = json.loads(collector.body)
    assert set(envelope) == {"error"}
    error = envelope["error"]
    assert error["code"] == "payload_too_large"
    assert set(error) == {"code", "message", "details", "request_id"}


async def test_body_limit_rejects_oversized_content_length_before_app():
    app = BodyLimitMiddleware(
        _echo_app(), settings=_settings(max_json_body_bytes=100, max_upload_size_bytes=1000)
    )
    send = _SendCollector()

    async def forbidden_receive() -> Message:
        raise AssertionError("body must not be read when Content-Length exceeds the limit")

    await app(
        _scope(headers={"content-type": "application/json", "content-length": "500"}),
        forbidden_receive,
        send,
    )
    _assert_payload_too_large(send)


async def test_body_limit_aborts_streamed_json_body():
    app = BodyLimitMiddleware(
        _echo_app(), settings=_settings(max_json_body_bytes=100, max_upload_size_bytes=1000)
    )
    send = _SendCollector()
    calls: list[int] = []
    await app(
        _scope(headers={"content-type": "application/json"}),
        _chunked_receive([b"x" * 60, b"x" * 60, b"x" * 60], calls),
        send,
    )
    _assert_payload_too_large(send)
    assert len(calls) <= 2


async def test_body_limit_multipart_gets_upload_limit_plus_overhead():
    settings = _settings(max_json_body_bytes=100, max_upload_size_bytes=100)
    multipart_limit = 100 + _MB
    send = _SendCollector()
    await BodyLimitMiddleware(_echo_app(), settings=settings)(
        _scope(
            headers={
                "content-type": "multipart/form-data; boundary=x",
                "content-length": str(multipart_limit),
            }
        ),
        _disconnect_receive,
        send,
    )
    assert send.status == 200

    send = _SendCollector()
    await BodyLimitMiddleware(_echo_app(), settings=settings)(
        _scope(
            headers={
                "content-type": "multipart/form-data; boundary=x",
                "content-length": str(multipart_limit + 1),
            }
        ),
        _disconnect_receive,
        send,
    )
    _assert_payload_too_large(send)

    send = _SendCollector()
    await BodyLimitMiddleware(_echo_app(), settings=settings)(
        _scope(
            headers={"content-type": "application/json", "content-length": str(multipart_limit)}
        ),
        _disconnect_receive,
        send,
    )
    _assert_payload_too_large(send)


async def test_body_limit_aborts_streamed_multipart_body():
    app = BodyLimitMiddleware(
        _echo_app(), settings=_settings(max_upload_size_bytes=0, max_json_body_bytes=100)
    )
    send = _SendCollector()
    await app(
        _scope(headers={"content-type": "multipart/form-data; boundary=x"}),
        _chunked_receive([b"y" * 600_000, b"y" * 600_000]),
        send,
    )
    _assert_payload_too_large(send)


async def test_body_limit_allows_body_within_limit():
    app = BodyLimitMiddleware(_echo_app(), settings=_settings(max_json_body_bytes=100))
    send = _SendCollector()
    await app(
        _scope(headers={"content-type": "application/json"}),
        _chunked_receive([b"x" * 50, b"x" * 50]),
        send,
    )
    assert send.status == 200


@pytest.mark.parametrize(
    ("path", "expect_no_store", "expect_csp"),
    [
        ("/api/v1/uploads", True, False),
        ("/docs", False, True),
        ("/docs/oauth2-redirect", False, True),
        ("/health/live", False, False),
    ],
)
async def test_security_headers(path, expect_no_store, expect_csp):
    app = SecurityHeadersMiddleware(_echo_app())
    send = _SendCollector()
    await app(_scope(path=path, method="GET"), _disconnect_receive, send)
    assert send.status == 200
    assert send.header("x-content-type-options") == "nosniff"
    assert send.header("x-frame-options") == "DENY"
    assert send.header("referrer-policy") == "no-referrer"
    assert (send.header("cache-control") == "no-store") is expect_no_store
    assert (send.header("content-security-policy") == "frame-ancestors 'none'") is expect_csp


async def test_request_id_truncated_to_64_chars():
    app = RequestContextMiddleware(_echo_app())
    send = _SendCollector()
    await app(
        _scope(path="/api/v1/auth/me", method="GET", headers={"x-request-id": "a" * 200}),
        _disconnect_receive,
        send,
    )
    assert send.header("x-request-id") == "a" * 64


async def test_unmatched_route_uses_constant_metrics_label():
    async def not_found_app(scope: Scope, receive: Receive, send: Send) -> None:
        await send({"type": "http.response.start", "status": 404, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    counter = metrics.HTTP_REQUESTS.labels("GET", "<unmatched>", "404")
    before = counter._value.get()
    send = _SendCollector()
    await RequestContextMiddleware(not_found_app)(
        _scope(path="/definitely-not-a-route-12345", method="GET"), _disconnect_receive, send
    )
    assert counter._value.get() == before + 1


async def test_matched_route_uses_path_template_label():
    async def matched_app(scope: Scope, receive: Receive, send: Send) -> None:
        scope["route"] = SimpleNamespace(path="/api/v1/things/{thing_id}")
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    counter = metrics.HTTP_REQUESTS.labels("GET", "/api/v1/things/{thing_id}", "200")
    before = counter._value.get()
    send = _SendCollector()
    await RequestContextMiddleware(matched_app)(
        _scope(path="/api/v1/things/abc", method="GET"), _disconnect_receive, send
    )
    assert counter._value.get() == before + 1


class _BrokenRedis:
    def pipeline(self) -> Any:
        raise RedisError("connection refused")


async def test_ratelimit_redis_outage_falls_back_to_shared_singleton():
    key = f"fallback-{uuid.uuid4()}"
    first = RateLimiter(_BrokenRedis())
    second = RateLimiter(_BrokenRedis())
    await first.check(key, 2)
    await first.check(key, 2)
    with pytest.raises(RateLimitError):
        await second.check(key, 2)


async def test_ratelimit_redis_outage_still_enforces_within_instance():
    key = f"fallback-{uuid.uuid4()}"
    limiter = RateLimiter(_BrokenRedis())
    for _ in range(3):
        await limiter.check(key, 3)
    with pytest.raises(RateLimitError):
        await limiter.check(key, 3)


class _RecordingPipeline:
    def __init__(self, members: list[str]) -> None:
        self._members = members

    def zremrangebyscore(self, *args: Any) -> None:
        pass

    def zadd(self, key: str, mapping: dict[str, float]) -> None:
        self._members.extend(mapping)

    def zcard(self, key: str) -> None:
        pass

    def expire(self, *args: Any) -> None:
        pass

    async def execute(self) -> list[Any]:
        return [0, 1, len(self._members), True]


class _RecordingRedis:
    def __init__(self) -> None:
        self.members: list[str] = []

    def pipeline(self) -> _RecordingPipeline:
        return _RecordingPipeline(self.members)


async def test_ratelimit_zset_members_are_unique():
    redis = _RecordingRedis()
    limiter = RateLimiter(redis)
    await limiter.check("unique-members", 10)
    await limiter.check("unique-members", 10)
    assert len(redis.members) == 2
    assert redis.members[0] != redis.members[1]


async def test_login_unknown_user_runs_dummy_verify(monkeypatch):
    service = AuthService(session=None, settings=_settings())  # type: ignore[arg-type]

    async def no_user(username: str) -> None:
        return None

    monkeypatch.setattr(service._users, "get_by_username", no_user)
    calls: list[str] = []
    real_verify = auth_service_module.verify_password

    def spy(password: str, password_hash: str) -> bool:
        calls.append(password_hash)
        return real_verify(password, password_hash)

    monkeypatch.setattr(auth_service_module, "verify_password", spy)
    with pytest.raises(AuthenticationError):
        await service.login("ghost", "whatever")
    assert calls == [DUMMY_PASSWORD_HASH]


async def test_login_inactive_user_runs_dummy_verify(monkeypatch):
    service = AuthService(session=None, settings=_settings())  # type: ignore[arg-type]
    inactive = SimpleNamespace(is_active=False, password_hash="real-hash")

    async def get_inactive(username: str) -> Any:
        return inactive

    monkeypatch.setattr(service._users, "get_by_username", get_inactive)
    calls: list[str] = []
    monkeypatch.setattr(
        auth_service_module,
        "verify_password",
        lambda password, password_hash: calls.append(password_hash) or False,
    )
    with pytest.raises(AuthenticationError):
        await service.login("disabled", "whatever")
    assert calls == [DUMMY_PASSWORD_HASH]


class _SetRecordingRedis:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, int | None]] = []

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        self.calls.append((key, value, ex))


async def test_logout_sets_denylist_key_with_remaining_ttl():
    service = AuthService(session=None, settings=_settings())  # type: ignore[arg-type]
    redis = _SetRecordingRedis()
    await service.logout({"jti": "j-1", "exp": int(time.time()) + 120}, redis)
    assert len(redis.calls) == 1
    key, _, ttl = redis.calls[0]
    assert key == "jwt:deny:j-1"
    assert ttl is not None and 118 <= ttl <= 120


async def test_logout_expired_token_skips_denylist():
    service = AuthService(session=None, settings=_settings())  # type: ignore[arg-type]
    redis = _SetRecordingRedis()
    await service.logout({"jti": "j-2", "exp": int(time.time()) - 10}, redis)
    assert redis.calls == []


@pytest.mark.parametrize(
    ("brand", "expected"),
    [
        (b"isom", ("video/mp4", MediaType.VIDEO)),
        (b"mp42", ("video/mp4", MediaType.VIDEO)),
        (b"3gp5", ("video/mp4", MediaType.VIDEO)),
        (b"qt  ", ("video/quicktime", MediaType.VIDEO)),
        (b"heic", None),
        (b"mif1", None),
        (b"avif", None),
    ],
)
def test_ftyp_brand_allowlist(brand, expected):
    header = b"\x00\x00\x00\x18ftyp" + brand + b"\x00" * 8
    assert sniff_media_type(header) == expected


def _foreign_upload(data: bytes) -> Upload:
    return Upload(
        id=uuid.uuid4(),
        original_filename="secret.jpg",
        storage_key="uploads/other/secret.jpg",
        content_type="image/jpeg",
        file_size=len(data),
        checksum_sha256=hashlib.sha256(data).hexdigest(),
        media_type=MediaType.IMAGE,
        uploaded_by=uuid.uuid4(),
        route_id=uuid.uuid4(),
        metadata_={"gps_track": [{"lat": 55.7, "lon": 37.6}]},
        created_at=datetime.now(UTC),
    )


def _upload_service(session: Any = None, storage: Any = None) -> UploadService:
    return UploadService(
        session=session if session is not None else object(),
        storage=storage if storage is not None else object(),
        settings=_settings(),
    )


def _reader(data: bytes) -> Any:
    chunks = iter([data])

    async def read_chunk() -> bytes:
        return next(chunks, b"")

    return read_chunk


async def test_dedup_foreign_upload_is_redacted(monkeypatch):
    data = b"\xff\xd8\xff\xe0" + b"\x00" * 32
    foreign = _foreign_upload(data)
    service = _upload_service()

    async def get_by_checksum(self: UploadRepository, checksum: str) -> Upload:
        return foreign

    monkeypatch.setattr(UploadRepository, "get_by_checksum", get_by_checksum)
    requester = uuid.uuid4()
    result = await service.create_upload(
        read_chunk=_reader(data),
        filename="probe.jpg",
        content_type="image/jpeg",
        uploaded_by=requester,
        requester_id=requester,
        requester_role=UserRole.OPERATOR,
    )
    assert result.created is False
    assert result.redacted is True
    redacted = result.upload
    assert redacted.id == foreign.id
    assert redacted.checksum_sha256 == foreign.checksum_sha256
    assert redacted.file_size == foreign.file_size
    assert redacted.media_type == foreign.media_type
    assert redacted.created_at == foreign.created_at
    assert redacted.original_filename == "[redacted]"
    assert redacted.storage_key == "[redacted]"
    assert redacted.content_type == "application/octet-stream"
    assert redacted.metadata_ == {}
    assert redacted.uploaded_by is None
    assert redacted.route_id is None
    assert foreign.metadata_["gps_track"]


@pytest.mark.parametrize("as_admin", [False, True])
async def test_dedup_owner_or_admin_sees_full_record(monkeypatch, as_admin):
    data = b"\xff\xd8\xff\xe0" + b"\x00" * 32
    foreign = _foreign_upload(data)
    service = _upload_service()

    async def get_by_checksum(self: UploadRepository, checksum: str) -> Upload:
        return foreign

    monkeypatch.setattr(UploadRepository, "get_by_checksum", get_by_checksum)
    requester = uuid.uuid4() if as_admin else foreign.uploaded_by
    result = await service.create_upload(
        read_chunk=_reader(data),
        filename="probe.jpg",
        content_type="image/jpeg",
        uploaded_by=requester,
        requester_id=requester,
        requester_role=UserRole.ADMIN if as_admin else UserRole.OPERATOR,
    )
    assert result.created is False
    assert result.redacted is False
    assert result.upload is foreign


@pytest.mark.parametrize("role", [UserRole.OPERATOR, UserRole.VIEWER, UserRole.SERVICE])
async def test_delete_denied_for_non_owner_non_admin(role):
    upload = _foreign_upload(b"\xff\xd8\xff\xe0" + b"\x00" * 32)
    service = _upload_service()
    with pytest.raises(PermissionDeniedError):
        await service.delete_upload(upload, actor_id=uuid.uuid4(), actor_role=role)


class _FakeResult:
    def scalar_one(self) -> int:
        return 0


class _FakeSession:
    def __init__(self) -> None:
        self.info: dict[str, Any] = {}
        self.deleted: list[Any] = []

    async def execute(self, stmt: Any) -> _FakeResult:
        return _FakeResult()

    async def flush(self) -> None:
        pass

    async def delete(self, instance: Any) -> None:
        self.deleted.append(instance)

    def add(self, instance: Any) -> None:
        pass


class _ForbiddenStorage:
    async def delete(self, key: str) -> None:
        raise AssertionError("storage must not be touched before commit")


@pytest.mark.parametrize(
    ("actor_role", "foreign_actor"),
    [(UserRole.ADMIN, True), (UserRole.OPERATOR, False)],
)
async def test_delete_defers_storage_removal_until_after_commit(actor_role, foreign_actor):
    upload = _foreign_upload(b"\xff\xd8\xff\xe0" + b"\x00" * 32)
    session = _FakeSession()
    service = _upload_service(session=session, storage=_ForbiddenStorage())
    actor_id = uuid.uuid4() if foreign_actor else upload.uploaded_by
    await service.delete_upload(upload, actor_id=actor_id, actor_role=actor_role)
    assert session.info["storage_delete_keys"] == [upload.storage_key]
    assert session.deleted == [upload]


@pytest.mark.parametrize(
    ("role", "expected"),
    [
        (UserRole.ADMIN, True),
        (UserRole.OPERATOR, True),
        (UserRole.SERVICE, True),
        (UserRole.VIEWER, False),
    ],
)
def test_can_access_media_matrix(role, expected):
    user = User(username="u", password_hash="x", role=role)
    assert can_access_media(user) is expected
