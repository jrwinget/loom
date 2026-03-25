from uuid import UUID

import magic
from sqlalchemy.ext.asyncio import AsyncSession

from loom.models.asset import Asset
from loom.models.chain_of_custody import ChainOfCustodyEntry

ALLOWED_MEDIA_TYPES: dict[str, list[str]] = {
    "video": [
        "video/mp4",
        "video/quicktime",
        "video/x-msvideo",
        "video/x-matroska",
        "video/webm",
    ],
    "image": [
        "image/jpeg",
        "image/png",
        "image/tiff",
        "image/heic",
    ],
    "audio": [
        "audio/mpeg",
        "audio/wav",
        "audio/aac",
        "audio/flac",
        "audio/ogg",
    ],
    "document": [
        "application/pdf",
        "application/vnd.openxmlformats-officedocument"
        ".wordprocessingml.document",
        "text/plain",
    ],
}

# reverse lookup: mime -> media_type
_MIME_TO_MEDIA: dict[str, str] = {}
for _media_type, _mimes in ALLOWED_MEDIA_TYPES.items():
    for _mime in _mimes:
        _MIME_TO_MEDIA[_mime] = _media_type


def detect_media_type(mime_type: str) -> str | None:
    """map mime to media_type category."""
    return _MIME_TO_MEDIA.get(mime_type)


def validate_file_type(
    data: bytes,
    filename: str,
) -> tuple[str, str]:
    """detect mime from magic bytes and validate.

    returns (mime_type, media_type). raises ValueError if
    file type is not in the allowed list.
    """
    mime_type = magic.from_buffer(data, mime=True)
    media_type = detect_media_type(mime_type)

    if media_type is None:
        msg = f"file type '{mime_type}' is not allowed for '{filename}'"
        raise ValueError(msg)

    return mime_type, media_type


def generate_storage_key(
    case_id: str,
    asset_id: str,
    filename: str,
) -> str:
    """returns {case_id}/{asset_id}/{filename}."""
    return f"{case_id}/{asset_id}/{filename}"


async def create_asset_record(
    session: AsyncSession,
    case_id: str,
    filename: str,
    storage_key: str,
    media_type: str,
    mime_type: str,
    file_size: int,
    sha256: str,
    sha512: str,
    user_id: str,
) -> Asset:
    """create asset in db with upload_status='complete'."""
    asset = Asset(
        case_id=UUID(case_id),
        original_filename=filename,
        storage_key=storage_key,
        media_type=media_type,
        mime_type=mime_type,
        file_size_bytes=file_size,
        sha256_hash=sha256,
        sha512_hash=sha512,
        upload_status="complete",
        uploaded_by=UUID(user_id),
        processing_status="pending",
    )
    session.add(asset)
    await session.flush()
    await session.refresh(asset)
    return asset


async def record_upload_custody(
    session: AsyncSession,
    asset_id: str,
    user_id: str,
    ip_address: str | None,
) -> None:
    """write chain_of_custody entry for upload."""
    entry = ChainOfCustodyEntry(
        asset_id=UUID(asset_id),
        action="upload",
        actor_id=UUID(user_id),
        detail={"action": "file_uploaded"},
        ip_address=ip_address,
    )
    session.add(entry)
    await session.flush()
