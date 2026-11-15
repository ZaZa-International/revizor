from __future__ import annotations

from app.application.interfaces.storage import ObjectStorage
from app.config import Settings
from app.infrastructure.storage.local import LocalFilesystemStorage
from app.infrastructure.storage.s3 import S3Storage


def build_storage(settings: Settings) -> ObjectStorage:
    if settings.storage_backend == "local":
        return LocalFilesystemStorage(settings.storage_local_path)
    return S3Storage(settings)
