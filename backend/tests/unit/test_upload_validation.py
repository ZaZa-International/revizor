import pytest
from app.application.services.uploads import sanitize_filename, sniff_media_type
from app.core.exceptions import ValidationAppError
from app.domain.enums import MediaType
from app.infrastructure.storage.local import safe_join

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("video.mp4", "video.mp4"),
        ("../../etc/passwd", "passwd"),
        ("/abs/path/file.jpg", "file.jpg"),
        ("a b/c*d.png", "c_d.png"),
        ("...", "upload.bin"),
        ("", "upload.bin"),
    ],
)
def test_sanitize_filename(raw, expected):
    assert sanitize_filename(raw) == expected


def test_sniff_jpeg():
    assert sniff_media_type(b"\xff\xd8\xff\xe0rest") == ("image/jpeg", MediaType.IMAGE)


def test_sniff_png():
    assert sniff_media_type(b"\x89PNG\r\n\x1a\nrest") == ("image/png", MediaType.IMAGE)


def test_sniff_mp4():
    header = b"\x00\x00\x00\x18ftypisom" + b"\x00" * 8
    assert sniff_media_type(header) == ("video/mp4", MediaType.VIDEO)


def test_sniff_unknown():
    assert sniff_media_type(b"MZ\x90\x00executable") is None


def test_safe_join_blocks_traversal(tmp_path):
    with pytest.raises(ValidationAppError):
        safe_join(tmp_path, "../escape.txt")
    with pytest.raises(ValidationAppError):
        safe_join(tmp_path, "/etc/passwd")
    with pytest.raises(ValidationAppError):
        safe_join(tmp_path, "a/../../escape.txt")
    ok = safe_join(tmp_path, "uploads/x/file.jpg")
    assert ok.is_relative_to(tmp_path)
