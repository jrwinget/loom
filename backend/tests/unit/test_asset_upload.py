"""tests for streaming upload and temp file safety in assets api."""

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
    """mock upload file that yields data in chunks."""

    def __init__(self, data: bytes, chunk_size: int = 64 * 1024) -> None:
        self._stream = BytesIO(data)
        self._chunk_size = chunk_size
        self.filename = "test.bin"
        self.read_count = 0

    async def read(self, size: int = -1) -> bytes:
        self.read_count += 1
        return self._stream.read(size)


class _SavepointStub:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


class _StubSession:
    async def flush(self) -> None:
        pass

    async def commit(self) -> None:
        pass

    async def refresh(self, obj: object) -> None:
        pass

    def begin_nested(self):
        return _SavepointStub()


_SVC = "loom.api.v1.assets"


@pytest.mark.asyncio
async def test_upload_rejects_oversized_file_early() -> None:
    """chunked reader should reject file exceeding 100mb
    without reading entire content into memory."""
    # build a file slightly over the limit
    oversized = b"\x00" * (_MAX_UPLOAD_SIZE + 1)
    fake_file = _FakeUploadFile(oversized)

    mock_request = MagicMock(spec=Request)
    mock_request.client.host = "127.0.0.1"
    mock_request.headers = {}
    mock_request.state = MagicMock()
    db = _StubSession()
    minio = MagicMock()

    token_payload = {"sub": "user-1", "role": "analyst"}

    with (
        patch(
            f"{_SVC}._check_access",
            new_callable=AsyncMock,
            return_value=True,
        ),
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

    # the key assertion: file was not fully read into memory.
    # with 64kb chunks, reading 100mb+1 should stop well
    # before reading every byte if we had a single read().
    # the read count should be > 1 (chunked) and the stream
    # position should be <= _MAX_UPLOAD_SIZE + chunk_size.
    assert fake_file.read_count > 1


@pytest.mark.asyncio
async def test_upload_reads_in_chunks() -> None:
    """chunked reading uses multiple read calls, not one."""
    content = b"\xff\xd8\xff" + b"\x00" * 200_000  # 200kb
    fake_file = _FakeUploadFile(content, chunk_size=64 * 1024)

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

    # 200kb at 64kb chunks = at least 4 reads + 1 final empty
    assert fake_file.read_count >= 4


@pytest.mark.asyncio
async def test_presigned_temp_file_cleaned_on_error() -> None:
    """temp file must be removed even when hashing raises."""
    # create a real temp file to verify cleanup
    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        tmp.write(b"test data")
        real_tmp_path = tmp.name

    assert Path(real_tmp_path).exists()

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

    class _FakeTmpCtx:
        def __enter__(self_inner):  # noqa: N805
            obj = MagicMock()
            obj.name = real_tmp_path
            return obj

        def __exit__(self_inner, *a):  # noqa: N805
            pass

    def _fake_named_temp(**kwargs):  # type: ignore[no-untyped-def]
        """return a context manager yielding our real file."""
        return _FakeTmpCtx()

    with (
        patch(
            f"{_SVC}._check_access",
            new_callable=AsyncMock,
            return_value=True,
        ),
        patch(f"{_SVC}.StorageService") as mock_storage_cls,
        patch(
            f"{_SVC}.tempfile.NamedTemporaryFile",
            side_effect=_fake_named_temp,
        ),
        patch(
            f"{_SVC}.compute_hashes_from_file",
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

    # temp file should have been cleaned up by finally block
    assert not Path(real_tmp_path).exists()


@pytest.mark.asyncio
async def test_presigned_temp_file_cleaned_on_success() -> None:
    """temp file must be removed on the happy path too."""
    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        tmp.write(b"\xff\xd8\xff" + b"\x00" * 100)
        real_tmp_path = tmp.name

    assert Path(real_tmp_path).exists()

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

    class _FakeTmpCtx2:
        def __enter__(self_inner):  # noqa: N805
            obj = MagicMock()
            obj.name = real_tmp_path
            return obj

        def __exit__(self_inner, *a):  # noqa: N805
            pass

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
            f"{_SVC}.tempfile.NamedTemporaryFile",
            side_effect=lambda **kw: _FakeTmpCtx2(),
        ),
        patch(
            f"{_SVC}.compute_hashes_from_file",
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
    # temp file should be cleaned up
    assert not Path(real_tmp_path).exists()
