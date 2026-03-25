from unittest.mock import patch

import pytest

from loom.services.ingest import (
    detect_media_type,
    generate_storage_key,
    validate_file_type,
)


def test_detect_media_type_video() -> None:
    """video mime types map to 'video'."""
    assert detect_media_type("video/mp4") == "video"
    assert detect_media_type("video/quicktime") == "video"


def test_detect_media_type_image() -> None:
    """image mime types map to 'image'."""
    assert detect_media_type("image/jpeg") == "image"
    assert detect_media_type("image/png") == "image"


def test_detect_media_type_audio() -> None:
    """audio mime types map to 'audio'."""
    assert detect_media_type("audio/mpeg") == "audio"
    assert detect_media_type("audio/wav") == "audio"


def test_detect_media_type_document() -> None:
    """document mime types map to 'document'."""
    assert detect_media_type("application/pdf") == "document"
    assert detect_media_type("text/plain") == "document"


def test_detect_media_type_unknown() -> None:
    """unknown mime types return None."""
    assert detect_media_type("application/octet-stream") is None
    assert detect_media_type("text/html") is None


def test_validate_file_type_valid() -> None:
    """valid file types are accepted."""
    with patch(
        "loom.services.ingest.magic.from_buffer",
        return_value="image/jpeg",
    ):
        mime, media = validate_file_type(b"\xff\xd8\xff", "photo.jpg")
        assert mime == "image/jpeg"
        assert media == "image"


def test_validate_file_type_invalid() -> None:
    """disallowed types raise ValueError."""
    with (
        patch(
            "loom.services.ingest.magic.from_buffer",
            return_value="application/x-executable",
        ),
        pytest.raises(ValueError, match="not allowed"),
    ):
        validate_file_type(b"\x7fELF", "malware.exe")


def test_generate_storage_key_format() -> None:
    """storage key follows case_id/asset_id/filename."""
    key = generate_storage_key("case-123", "asset-456", "evidence.mp4")
    assert key == "case-123/asset-456/evidence.mp4"
