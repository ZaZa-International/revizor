"""Local filesystem storage for tests and lightweight development.

Keys are sanitized against path traversal. Presigned URLs are not supported;
the API serves files through an authenticated download endpoint instead.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import anyio

from app.application.interfaces.storage import ObjectMetadata
from app.core.exceptions import StorageError, StorageObjectNotFoundError, ValidationAppError


def safe_join(root: Path, key: str) -> Path:
    if not key or key.startswith("/") or ".." in key.split("/") or "\\" in key:
        raise ValidationAppError(f"Unsafe storage key: {key!r}")
    candidate = (root / key).resolve()
    if not candidate.is_relative_to(root.resolve()):
        raise ValidationAppError(f"Unsafe storage key: {key!r}")
    return candidate


class LocalFilesystemStorage:
    def __init__(self, root: str) -> None:
        self._root = Path(root).resolve()
        self._root.mkdir(parents=True, exist_ok=True)

    async def upload(self, key: str, data: bytes, content_type: str) -> None:
        path = safe_join(self._root, key)
        await anyio.to_thread.run_sync(self._write, path, data, content_type)

    def _write(self, path: Path, data: bytes, content_type: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        path.with_suffix(path.suffix + ".meta").write_text(content_type)

    async def upload_file(self, key: str, path: str, content_type: str) -> None:
        data = await anyio.to_thread.run_sync(Path(path).read_bytes)
        await self.upload(key, data, content_type)

    async def download(self, key: str) -> bytes:
        path = safe_join(self._root, key)
        try:
            return await anyio.to_thread.run_sync(path.read_bytes)
        except FileNotFoundError as exc:
            raise StorageObjectNotFoundError(key) from exc

    async def download_to_file(self, key: str, path: str) -> None:
        data = await self.download(key)
        await anyio.to_thread.run_sync(Path(path).write_bytes, data)

    async def delete(self, key: str) -> None:
        path = safe_join(self._root, key)

        def _delete() -> None:
            path.unlink(missing_ok=True)
            path.with_suffix(path.suffix + ".meta").unlink(missing_ok=True)

        await anyio.to_thread.run_sync(_delete)

    async def exists(self, key: str) -> bool:
        path = safe_join(self._root, key)
        return await anyio.to_thread.run_sync(path.is_file)

    async def generate_presigned_url(
        self, key: str, expires_seconds: int = 3600, method: str = "GET"
    ) -> str:
        if not await self.exists(key):
            raise StorageObjectNotFoundError(key)
        return f"/api/v1/files/{key}"

    async def get_metadata(self, key: str) -> ObjectMetadata:
        path = safe_join(self._root, key)
        if not path.is_file():
            raise StorageObjectNotFoundError(key)

        def _meta() -> ObjectMetadata:
            meta_path = path.with_suffix(path.suffix + ".meta")
            content_type = (
                meta_path.read_text().strip() if meta_path.exists() else "application/octet-stream"
            )
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            return ObjectMetadata(
                size=path.stat().st_size, content_type=content_type, checksum_sha256=digest
            )

        try:
            return await anyio.to_thread.run_sync(_meta)
        except OSError as exc:
            raise StorageError("Local storage read failed") from exc

    async def close(self) -> None:
        return None
