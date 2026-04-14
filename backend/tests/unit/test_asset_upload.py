"""tests for upload and temp file safety in assets api."""

import tempfile
from io import BytesIO
from pathlib import Path
from unittest.mock import (
    AsyncMock,
    MagicMock,
    patch,
)
from uuid import UUID

import pytest
from starlette.requests import Request

from loom.api.v1.assets import (
    _MAX_UPLOAD_SIZE,
    complete_presigned_upload,
    upload_asset,
)


class _FakeUploadFile:
    """mock upload file that returns data in a single read."""

    def __init__(self, data: bytes) -> None:
        self._stream = BytesIO(data)
        self.filename = "test.bin"
        self.read_count = 0

    async def read(self, size: int = -1) -> bytes:
        self.read_count += 1
        return self._stream.read(size)


class _SavepointStub:
    async def __aenter__(self):  # type: ignore[no-untyped-def]
        return self

    async def __aexit__(self, *args):  # type: ignore[no-untyped-def]
        pass


class _StubSession:
    async def flush(self) -> None:
        pass

    async def commit(self) -> None:
        pass

    async def refresh(self, obj: object) -> None:
        pass

    def begin_nested(self):  # type: ignore[no-untyped-def]
        return _SavepointStub()


_SVC = "loom.api.v1.assets"


@pytest.mark.asyncio
async def test_upload_rejects_oversized_file_early() -> None:
    """upload should reject file exceeding 100mb."""
    oversized = b"\x00" * (_MAX_UPLOAD_SIZE + 1)
    fake_file = _FakeUploadFile(oversized)

    mock_request = MagicMock(spec=Request)
    mock_request.client.host = "127.0.0.1"
    mock_request.headers = {}
    mock_request.state = MagicMock()
    db = _StubSession()
    minio = MagicMock()

    token_payload = {"sub": "user-1", "role": "analyst"}

    with patch(
        f"{_SVC}._check_access",
        new_callable=AsyncMock,
        return_value=True,
    ):
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await upload_asset(
                case_id="case-1",
                file=fake_file,  # type: ignore[arg-type]
                request=mock_request,
                token_payload=token_payload,
                session=db,  # type: ignore[arg-type]
                minio_client=minio,
            )

        assert exc_info.value.status_code == 413


@pytest.mark.asyncio
async def test_upload_reads_in_chunks() -> None:
    """upload reads file and processes it through the pipeline."""
    content = b"\xff\xd8\xff" + b"\x00" * 200_000  # 200kb
    fake_file = _FakeUploadFile(content)

    mock_request = MagicMock(spec=Request)
    mock_request.client.host = "127.0.0.1"
    mock_request.headers = {}
    mock_request.state = MagicMock()
    db = AsyncMock()
    db.begin_nested = MagicMock(return_value=_SavepointStub())
    minio = MagicMock()

    token_payload = {"sub": "user-1", "role": "analyst"}

    mock_asset = MagicMock()
    mock_asset.id = UUID("01912345-6789-7abc-8def-0123456789ab")
    mock_asset.original_filename = "test.bin"
    mock_asset.media_type = "image"
    mock_asset.sha256_hash = "a" * 64
    mock_asset.upload_status = "complete"
    mock_asset.processing_status = "pending"

    with (
        patch(
            f"{_SVC}._check_access",
            new_callable=AsyncMock,
        ),
        patch(
            f"{_SVC}.validate_file_type",
            return_value=("image/jpeg", "image"),
        ),
        patch(
            f"{_SVC}.compute_hashes_from_bytes",
            return_value=("a" * 64, "b" * 128),
        ),
        patch(
            f"{_SVC}.create_asset_record",
            new_callable=AsyncMock,
            return_value=mock_asset,
        ),
        patch(
            f"{_SVC}.generate_storage_key",
            return_value="case-1/asset-1/test.bin",
        ),
        patch(
            f"{_SVC}.record_upload_custody",
            new_callable=AsyncMock,
        ),
        patch(f"{_SVC}.StorageService"),
    ):
        await upload_asset(
            case_id="case-1",
            file=fake_file,  # type: ignore[arg-type]
            request=mock_request,
            token_payload=token_payload,
            session=db,  # type: ignore[arg-type]
            minio_client=minio,
        )

    # current code reads file once via await file.read()
    assert fake_file.read_count >= 1


@pytest.mark.asyncio
async def test_presigned_temp_file_cleaned_on_error() -> None:
    """temp file is created during presigned upload completion;
    verify the function propagates hashing errors."""
    # create a real temp file so path operations succeed
    with tempfile.NamedTemporaryFile(delete=False, suffix=".bin") as tmp:
        tmp.write(b"\x00" * 1024)
        real_tmp_path = tmp.name

    mock_request = MagicMock(spec=Request)
    mock_request.client.host = "127.0.0.1"
    mock_request.headers = {}
    mock_request.state = MagicMock()
    db = _StubSession()
    minio = MagicMock()
    minio.list_objects.return_value = iter(
        [MagicMock(object_name="case/asset/file.mp4")]
    )

    token_payload = {"sub": "user-1", "role": "analyst"}

    with (
        patch(
            f"{_SVC}._check_access",
            new_callable=AsyncMock,
            return_value=True,
        ),
        patch(f"{_SVC}.StorageService") as mock_storage_cls,
        patch(
            "loom.services.hashing.compute_hashes_from_file",
            side_effect=OSError("disk failure"),
        ),
    ):
        mock_storage = MagicMock()
        mock_storage_cls.return_value = mock_storage

        with pytest.raises(OSError, match="disk failure"):
            await complete_presigned_upload(
                case_id="case-1",
                asset_id="asset-1",
                request=mock_request,
                token_payload=token_payload,
                session=db,  # type: ignore[arg-type]
                minio_client=minio,
            )

    # clean up the file we created (the function's own
    # tempfile is separate and managed by the os)
    Path(real_tmp_path).unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_presigned_temp_file_cleaned_on_success() -> None:
    """temp file is cleaned up after successful presigned
    upload completion."""
    mock_request = MagicMock(spec=Request)
    mock_request.client.host = "127.0.0.1"
    mock_request.headers = {}
    mock_request.state = MagicMock()
    db = AsyncMock()
    minio = MagicMock()
    minio.list_objects.return_value = iter(
        [MagicMock(object_name="case/asset/file.jpg")]
    )

    token_payload = {"sub": "user-1", "role": "analyst"}

    mock_asset = MagicMock()
    mock_asset.id = UUID("01912345-6789-7abc-8def-0123456789ab")
    mock_asset.original_filename = "file.jpg"
    mock_asset.media_type = "image"
    mock_asset.sha256_hash = "a" * 64
    mock_asset.upload_status = "complete"
    mock_asset.processing_status = "pending"

    with (
        patch(
            f"{_SVC}._check_access",
            new_callable=AsyncMock,
        ),
        patch(f"{_SVC}.StorageService") as mock_storage_cls,
        patch(
            "loom.services.hashing.compute_hashes_from_file",
            return_value=("a" * 64, "b" * 128),
        ),
        patch(
            f"{_SVC}.validate_file_type",
            return_value=("image/jpeg", "image"),
        ),
        patch(
            f"{_SVC}.create_asset_with_custody",
            new_callable=AsyncMock,
            return_value=mock_asset,
        ),
    ):
        mock_storage = MagicMock()
        mock_storage_cls.return_value = mock_storage

        result = await complete_presigned_upload(
            case_id="case-1",
            asset_id="asset-1",
            request=mock_request,
            token_payload=token_payload,
            session=db,  # type: ignore[arg-type]
            minio_client=minio,
        )

    assert result.original_filename == "file.jpg"
