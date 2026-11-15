"""ObjectStorage abstraction: S3-compatible servers and local filesystem."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class ObjectMetadata:
    size: int
    content_type: str
    checksum_sha256: str | None = None


@runtime_checkable
class ObjectStorage(Protocol):
    async def upload(self, key: str, data: bytes, content_type: str) -> None: ...

    async def upload_file(self, key: str, path: str, content_type: str) -> None: ...

    async def download(self, key: str) -> bytes: ...

    async def download_to_file(self, key: str, path: str) -> None: ...

    async def delete(self, key: str) -> None: ...

    async def exists(self, key: str) -> bool: ...

    async def generate_presigned_url(
        self, key: str, expires_seconds: int = 3600, method: str = "GET"
    ) -> str: ...

    async def get_metadata(self, key: str) -> ObjectMetadata: ...

    async def close(self) -> None: ...
