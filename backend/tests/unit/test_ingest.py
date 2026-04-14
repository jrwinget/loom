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


@pytest.mark.asyncio
async def test_create_asset_record() -> None:
    """create_asset_record inserts asset with correct fields."""
    from unittest.mock import AsyncMock, MagicMock

    from loom.services.ingest import create_asset_record

    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    mock_session.flush = AsyncMock()

    # mock refresh to set id on the object
    async def _refresh(obj: object) -> None:
        pass

    mock_session.refresh = _refresh

    case_id = "01912345-6789-7abc-8def-0123456789ef"
    user_id = "01912345-6789-7abc-8def-0123456789ab"

    asset = await create_asset_record(
        mock_session,
        case_id,
        "photo.jpg",
        f"{case_id}/asset-1/photo.jpg",
        "image",
        "image/jpeg",
        2048,
        "a" * 64,
        "b" * 128,
        user_id,
    )

    mock_session.add.assert_called_once()
    assert asset.original_filename == "photo.jpg"
    assert asset.media_type == "image"
    assert asset.mime_type == "image/jpeg"
    assert asset.file_size_bytes == 2048
    assert asset.upload_status == "complete"
    assert asset.processing_status == "pending"


@pytest.mark.asyncio
async def test_record_upload_custody() -> None:
    """record_upload_custody creates chain_of_custody entry."""
    from unittest.mock import AsyncMock, MagicMock

    from loom.services.ingest import record_upload_custody

    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    mock_session.flush = AsyncMock()

    asset_id = "01912345-6789-7abc-8def-012345678902"
    user_id = "01912345-6789-7abc-8def-0123456789ab"

    await record_upload_custody(
        mock_session,
        asset_id,
        user_id,
        "192.168.1.1",
    )

    mock_session.add.assert_called_once()
    entry = mock_session.add.call_args[0][0]
    assert entry.action == "upload"
    assert entry.ip_address == "192.168.1.1"
    assert entry.detail == {"action": "file_uploaded"}


@pytest.mark.asyncio
async def test_record_upload_custody_no_ip() -> None:
    """record_upload_custody handles None ip_address."""
    from unittest.mock import AsyncMock, MagicMock

    from loom.services.ingest import record_upload_custody

    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    mock_session.flush = AsyncMock()

    asset_id = "01912345-6789-7abc-8def-012345678902"
    user_id = "01912345-6789-7abc-8def-0123456789ab"

    await record_upload_custody(
        mock_session,
        asset_id,
        user_id,
        None,
    )

    entry = mock_session.add.call_args[0][0]
    assert entry.ip_address is None
