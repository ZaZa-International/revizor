"""Storage integration: local filesystem + real S3-compatible server."""

from __future__ import annotations

import uuid

import httpx
import pytest
from app.config import Settings
from app.core.exceptions import StorageObjectNotFoundError, ValidationAppError
from app.infrastructure.storage.local import LocalFilesystemStorage
from app.infrastructure.storage.s3 import S3Storage

pytestmark = pytest.mark.integration


async def test_local_roundtrip(tmp_path):
    storage = LocalFilesystemStorage(str(tmp_path))
    key = f"uploads/{uuid.uuid4()}/test.jpg"
    await storage.upload(key, b"binary-data", "image/jpeg")
    assert await storage.exists(key)
    assert await storage.download(key) == b"binary-data"
    meta = await storage.get_metadata(key)
    assert meta.size == 11
    assert meta.content_type == "image/jpeg"
    url = await storage.generate_presigned_url(key)
    assert url.startswith("/api/v1/files/")
    await storage.delete(key)
    assert not await storage.exists(key)
    with pytest.raises(StorageObjectNotFoundError):
        await storage.download(key)


async def test_local_traversal_blocked(tmp_path):
    storage = LocalFilesystemStorage(str(tmp_path))
    with pytest.raises(ValidationAppError):
        await storage.upload("../evil.txt", b"x", "text/plain")


async def test_local_upload_file(tmp_path):
    storage = LocalFilesystemStorage(str(tmp_path / "store"))
    source = tmp_path / "source.bin"
    source.write_bytes(b"file-content")
    key = "frames/0001.jpg"
    await storage.upload_file(key, str(source), "image/jpeg")
    assert await storage.download(key) == b"file-content"


async def test_s3_roundtrip():
    settings = Settings(storage_backend="s3")
    storage = S3Storage(settings)
    await storage.ensure_bucket()
    key = f"tests/{uuid.uuid4()}/object.bin"
    try:
        await storage.upload(key, b"s3-payload", "application/octet-stream")
        assert await storage.exists(key)
        assert await storage.download(key) == b"s3-payload"
        meta = await storage.get_metadata(key)
        assert meta.size == 10
        url = await storage.generate_presigned_url(key, expires_seconds=120)
        assert "X-Amz-Signature" in url or "AWSAccessKeyId" in url
        async with httpx.AsyncClient() as client:
            response = await client.get(url)
        assert response.status_code == 200
        assert response.content == b"s3-payload"
    finally:
        await storage.delete(key)
        assert not await storage.exists(key)
        await storage.close()
