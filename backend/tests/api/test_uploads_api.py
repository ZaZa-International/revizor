"""Uploads API: multipart ingestion, validation, dedup, idempotency, lifecycle."""

from __future__ import annotations

import hashlib
import json
import uuid

import cv2
import numpy as np
import pytest

from tests.api.test_assets_api import seed_job, seed_upload
from tests.fixtures.media import make_jpeg_bytes

pytestmark = pytest.mark.api

_UPLOAD_FK_BUG = (
    "BUG: UploadService.create_upload adds Upload and StoredFile then flushes once "
    "(app/application/services/uploads.py:159-183); without an ORM relationship the "
    "unit of work inserts stored_files before uploads, violating "
    "fk_stored_files_upload_id_uploads, so every new upload returns 409"
)
_MIME_SNIFF_BUG = (
    "BUG: UploadService.create_upload compares only MediaType, not the sniffed MIME "
    "vs declared content_type (app/application/services/uploads.py:128); PNG bytes "
    "named .jpg with content_type image/jpeg are accepted instead of 422 "
    "(currently also masked by the stored_files FK bug)"
)
_UPLOAD_LIST_RESPONSE_BUG = (
    "BUG: GET /api/v1/uploads re-validates items against UploadResponse whose "
    "metadata field has validation_alias='metadata_' without populate_by_name "
    "(app/schemas/uploads.py:30); _upload_response dumps key 'metadata' "
    "(app/api/v1/uploads.py:106), so any non-empty list fails with "
    "ResponseValidationError 500"
)


async def _upload(
    client,
    headers,
    data: bytes,
    *,
    filename="frame.jpg",
    content_type="image/jpeg",
    metadata=None,
    idempotency_key=None,
):
    form = {}
    if metadata is not None:
        form["metadata"] = metadata if isinstance(metadata, str) else json.dumps(metadata)
    extra_headers = dict(headers)
    if idempotency_key is not None:
        extra_headers["Idempotency-Key"] = idempotency_key
    return await client.post(
        "/api/v1/uploads",
        headers=extra_headers,
        files={"file": (filename, data, content_type)},
        data=form,
    )


def _png_bytes() -> bytes:
    image = np.zeros((16, 16, 3), dtype=np.uint8)
    ok, buffer = cv2.imencode(".png", image)
    assert ok
    return buffer.tobytes()


async def test_upload_image_created(client, admin_headers):
    data = make_jpeg_bytes(seed=1)
    response = await _upload(client, admin_headers, data)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["created"] is True
    upload = body["upload"]
    uuid.UUID(upload["id"])
    assert upload["checksum_sha256"] == hashlib.sha256(data).hexdigest()
    assert upload["media_type"] == "IMAGE"
    assert upload["content_type"] == "image/jpeg"
    assert upload["file_size"] == len(data)
    assert isinstance(upload["presigned_url"], str) and upload["presigned_url"]


async def test_duplicate_same_bytes_returns_existing(client, admin_headers):
    data = make_jpeg_bytes(seed=2)
    first = await _upload(client, admin_headers, data)
    assert first.status_code == 201
    second = await _upload(client, admin_headers, data, filename="renamed.jpg")
    assert second.status_code == 200, second.text
    body = second.json()
    assert body["created"] is False
    assert body["upload"]["id"] == first.json()["upload"]["id"]
    listing = await client.get("/api/v1/uploads", headers=admin_headers)
    assert listing.json()["total"] == 1


async def test_exe_extension_rejected_422(client, admin_headers):
    response = await _upload(
        client,
        admin_headers,
        b"MZ\x90\x00fake-binary",
        filename="tool.exe",
        content_type="application/octet-stream",
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


async def test_png_magic_with_jpeg_declaration_rejected_422(client, admin_headers):
    response = await _upload(
        client, admin_headers, _png_bytes(), filename="photo.jpg", content_type="image/jpeg"
    )
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "validation_error"


async def test_empty_file_rejected_422(client, admin_headers):
    response = await _upload(client, admin_headers, b"", filename="empty.jpg")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


async def test_invalid_metadata_json_rejected_422(client, admin_headers):
    response = await _upload(
        client, admin_headers, make_jpeg_bytes(seed=3), metadata="{not-valid-json"
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


async def test_list_pagination_and_media_type_filter(client, admin_headers):
    for seed in (10, 11):
        response = await _upload(client, admin_headers, make_jpeg_bytes(seed=seed))
        assert response.status_code == 201
    await _assert_list_pagination_and_filter(client, admin_headers)


async def test_list_pagination_and_media_type_filter_seeded(client, admin_headers, database):
    await seed_upload(database)
    await seed_upload(database)
    await _assert_list_pagination_and_filter(client, admin_headers)


async def _assert_list_pagination_and_filter(client, headers):
    listing = await client.get("/api/v1/uploads", headers=headers)
    assert listing.status_code == 200
    body = listing.json()
    assert body["total"] == 2
    assert body["page"] == 1
    assert body["page_size"] == 20
    assert body["pages"] == 1
    assert len(body["items"]) == 2

    paged = await client.get("/api/v1/uploads", headers=headers, params={"page_size": 1, "page": 2})
    paged_body = paged.json()
    assert paged_body["pages"] == 2
    assert len(paged_body["items"]) == 1
    assert paged_body["page"] == 2

    images = await client.get("/api/v1/uploads", headers=headers, params={"media_type": "IMAGE"})
    assert images.json()["total"] == 2
    videos = await client.get("/api/v1/uploads", headers=headers, params={"media_type": "VIDEO"})
    assert videos.json()["total"] == 0
    assert videos.json()["items"] == []


async def test_get_upload_by_id_and_unknown_404(client, admin_headers):
    created = await _upload(client, admin_headers, make_jpeg_bytes(seed=4))
    upload_id = created.json()["upload"]["id"]
    await _assert_get_by_id_and_unknown(client, admin_headers, upload_id)


async def test_get_upload_by_id_and_unknown_404_seeded(client, admin_headers, database):
    upload_id = await seed_upload(database)
    await _assert_get_by_id_and_unknown(client, admin_headers, upload_id)


async def _assert_get_by_id_and_unknown(client, headers, upload_id):
    response = await client.get(f"/api/v1/uploads/{upload_id}", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(upload_id)
    assert body["media_type"] == "IMAGE"
    assert body["checksum_sha256"]

    missing = await client.get(f"/api/v1/uploads/{uuid.uuid4()}", headers=headers)
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "not_found"


async def test_delete_without_jobs_204_then_404(client, admin_headers):
    created = await _upload(client, admin_headers, make_jpeg_bytes(seed=5))
    upload_id = created.json()["upload"]["id"]
    await _assert_delete_without_jobs(client, admin_headers, upload_id)


async def test_delete_without_jobs_204_then_404_seeded(client, admin_headers, database):
    upload_id = await seed_upload(database)
    await _assert_delete_without_jobs(client, admin_headers, upload_id)


async def _assert_delete_without_jobs(client, headers, upload_id):
    deleted = await client.delete(f"/api/v1/uploads/{upload_id}", headers=headers)
    assert deleted.status_code == 204
    assert deleted.content == b""
    missing = await client.get(f"/api/v1/uploads/{upload_id}", headers=headers)
    assert missing.status_code == 404


async def test_delete_with_job_conflict_409(client, admin_headers):
    created = await _upload(client, admin_headers, make_jpeg_bytes(seed=6))
    upload_id = created.json()["upload"]["id"]
    job = await client.post("/api/v1/jobs", headers=admin_headers, json={"upload_id": upload_id})
    assert job.status_code == 201, job.text
    deleted = await client.delete(f"/api/v1/uploads/{upload_id}", headers=admin_headers)
    assert deleted.status_code == 409
    assert deleted.json()["error"]["code"] == "conflict"


async def test_delete_with_job_conflict_409_seeded(client, admin_headers, database):
    seeded = await seed_job(database)
    deleted = await client.delete(f"/api/v1/uploads/{seeded.upload_id}", headers=admin_headers)
    assert deleted.status_code == 409
    assert deleted.json()["error"]["code"] == "conflict"


async def test_idempotency_key_replay_identical_body(client, admin_headers):
    data = make_jpeg_bytes(seed=7)
    key = str(uuid.uuid4())
    first = await _upload(client, admin_headers, data, idempotency_key=key)
    assert first.status_code == 201, first.text
    replay = await _upload(client, admin_headers, data, idempotency_key=key)
    assert replay.status_code == first.status_code
    assert replay.json() == first.json()
    listing = await client.get("/api/v1/uploads", headers=admin_headers)
    assert listing.json()["total"] == 1
