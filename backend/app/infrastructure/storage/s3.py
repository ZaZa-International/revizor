"""S3-compatible object storage (MinIO, SeaweedFS, AWS S3, ...).

boto3 is synchronous; calls are offloaded to a threadpool so the async API
never blocks. Binary content never enters PostgreSQL.
"""

from __future__ import annotations

from typing import Any

import anyio
import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from app.application.interfaces.storage import ObjectMetadata
from app.config import Settings
from app.core.exceptions import StorageError, StorageObjectNotFoundError
from app.core.logging import get_logger

logger = get_logger(__name__)


class S3Storage:
    def __init__(self, settings: Settings, client: Any | None = None) -> None:
        self._bucket = settings.s3_bucket
        self._presign_expires = settings.s3_presign_expires_seconds
        self._client = client or boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint_url,
            aws_access_key_id=settings.s3_access_key,
            aws_secret_access_key=settings.s3_secret_key,
            region_name=settings.s3_region,
            config=Config(
                signature_version="s3v4",
                s3={"addressing_style": "path"},
                retries={"max_attempts": 2, "mode": "standard"},
            ),
        )

    async def _run(self, func: Any, *args: Any, **kwargs: Any) -> Any:
        try:
            return await anyio.to_thread.run_sync(lambda: func(*args, **kwargs))
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "")
            if code in ("404", "NoSuchKey", "NotFound"):
                raise StorageObjectNotFoundError(str(kwargs.get("Key", args))) from exc
            logger.error("s3_error", code=code, operation=func.__name__)
            raise StorageError(f"S3 operation failed: {code}") from exc
        except Exception as exc:
            logger.error("s3_unexpected_error", error=str(exc))
            raise StorageError("S3 storage unavailable") from exc

    async def ensure_bucket(self) -> None:
        try:
            await self._run(self._client.head_bucket, Bucket=self._bucket)
        except StorageObjectNotFoundError:
            await self._run(self._client.create_bucket, Bucket=self._bucket)
            logger.info("s3_bucket_created", bucket=self._bucket)
        except StorageError:
            raise

    async def upload(self, key: str, data: bytes, content_type: str) -> None:
        await self._run(
            self._client.put_object,
            Bucket=self._bucket,
            Key=key,
            Body=data,
            ContentType=content_type,
        )

    async def upload_file(self, key: str, path: str, content_type: str) -> None:
        await self._run(
            self._client.upload_file,
            Filename=path,
            Bucket=self._bucket,
            Key=key,
            ExtraArgs={"ContentType": content_type},
        )

    async def download(self, key: str) -> bytes:
        response = await self._run(self._client.get_object, Bucket=self._bucket, Key=key)
        body = response["Body"]
        try:
            return await anyio.to_thread.run_sync(body.read)
        finally:
            body.close()

    async def download_to_file(self, key: str, path: str) -> None:
        await self._run(self._client.download_file, Bucket=self._bucket, Key=key, Filename=path)

    async def delete(self, key: str) -> None:
        await self._run(self._client.delete_object, Bucket=self._bucket, Key=key)

    async def exists(self, key: str) -> bool:
        try:
            await self._run(self._client.head_object, Bucket=self._bucket, Key=key)
            return True
        except StorageObjectNotFoundError:
            return False

    async def generate_presigned_url(
        self, key: str, expires_seconds: int = 3600, method: str = "GET"
    ) -> str:
        client_method = "get_object" if method.upper() == "GET" else "put_object"
        url: str = await self._run(
            self._client.generate_presigned_url,
            ClientMethod=client_method,
            Params={"Bucket": self._bucket, "Key": key},
            ExpiresIn=expires_seconds or self._presign_expires,
        )
        return url

    async def get_metadata(self, key: str) -> ObjectMetadata:
        response = await self._run(self._client.head_object, Bucket=self._bucket, Key=key)
        return ObjectMetadata(
            size=int(response.get("ContentLength", 0)),
            content_type=response.get("ContentType", "application/octet-stream"),
        )

    async def close(self) -> None:
        await anyio.to_thread.run_sync(self._client.close)
