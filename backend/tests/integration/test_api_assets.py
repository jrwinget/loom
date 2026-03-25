from datetime import UTC, datetime
from unittest.mock import (
    AsyncMock,
    MagicMock,
    patch,
)
from uuid import UUID

import httpx
import pytest_asyncio

from loom.config import Settings, get_settings
from loom.dependencies import get_db_session, get_minio_client
from loom.models.asset import Asset
from loom.security.auth import create_access_token

# fixed uuids for test entities
_USER_ID = UUID("01912345-6789-7abc-8def-0123456789cd")
_CASE_ID = UUID("01912345-6789-7abc-8def-0123456789ef")
_ASSET_ID = UUID("01912345-6789-7abc-8def-012345678902")
_NOW = datetime(2025, 1, 1, tzinfo=UTC)

# module path prefix for patching
_SVC = "loom.api.v1.assets"


def _make_asset(
    *,
    asset_id: UUID = _ASSET_ID,
    case_id: UUID = _CASE_ID,
) -> MagicMock:
    """build a mock asset object."""
    a = MagicMock(spec=Asset)
    a.id = asset_id
    a.case_id = case_id
    a.original_filename = "test.jpg"
    a.storage_key = f"{case_id}/{asset_id}/test.jpg"
    a.media_type = "image"
    a.mime_type = "image/jpeg"
    a.file_size_bytes = 1024
    a.sha256_hash = "a" * 64
    a.sha512_hash = "b" * 128
    a.upload_status = "complete"
    a.uploaded_by = _USER_ID
    a.uploaded_at = _NOW
    a.metadata_raw = None
    a.metadata_extracted = None
    a.capture_time = None
    a.capture_location_lat = None
    a.capture_location_lon = None
    a.processing_status = "pending"
    a.created_at = _NOW
    a.updated_at = _NOW
    return a


class _StubSession:
    """minimal stub session for dependency override."""

    async def execute(self, stmt):
        return MagicMock()

    def add(self, obj):
        pass

    async def flush(self) -> None:
        pass

    async def commit(self) -> None:
        pass

    async def refresh(self, obj):
        pass

    async def delete(self, obj):
        pass


def _create_app(settings: Settings) -> object:
    """build a test app with stub db and minio."""
    get_settings.cache_clear()

    with patch(
        "loom.config.get_settings",
        return_value=settings,
    ):
        from loom.main import create_app

        application = create_app()

    async def override_db():
        yield _StubSession()

    mock_minio = MagicMock()
    application.dependency_overrides[get_db_session] = override_db
    application.dependency_overrides[get_minio_client] = lambda: mock_minio
    # prevent audit middleware from writing to db
    application.state.db_session_factory = None

    return application


@pytest_asyncio.fixture
def mock_settings() -> Settings:
    """override settings for tests."""
    return Settings(
        secret_key="test-secret-key",
        access_token_expire_minutes=15,
        refresh_token_expire_days=7,
        database_url="sqlite+aiosqlite:///",
    )


def _auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def test_upload_asset(
    mock_settings: Settings,
) -> None:
    """upload file returns 201 with correct response."""
    app = _create_app(mock_settings)
    asset = _make_asset()

    with (
        patch(
            "loom.security.auth.get_settings",
            return_value=mock_settings,
        ),
        patch(
            f"{_SVC}.check_case_access",
            new_callable=AsyncMock,
            return_value=True,
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
            return_value=asset,
        ),
        patch(
            f"{_SVC}.generate_storage_key",
            return_value=f"{_CASE_ID}/{_ASSET_ID}/test.jpg",
        ),
        patch(
            f"{_SVC}.record_upload_custody",
            new_callable=AsyncMock,
        ),
        patch(
            f"{_SVC}.StorageService",
        ) as mock_storage_cls,
    ):
        mock_storage = MagicMock()
        mock_storage_cls.return_value = mock_storage

        token = create_access_token(str(_USER_ID), "analyst")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            resp = await ac.post(
                f"/api/v1/cases/{_CASE_ID}/assets/upload",
                files={
                    "file": (
                        "test.jpg",
                        b"\xff\xd8\xff" + b"\x00" * 100,
                        "image/jpeg",
                    )
                },
                headers=_auth_header(token),
            )

    assert resp.status_code == 201
    data = resp.json()
    assert data["original_filename"] == "test.jpg"
    assert data["media_type"] == "image"
    assert data["upload_status"] == "complete"


async def test_upload_rejects_disallowed_type(
    mock_settings: Settings,
) -> None:
    """upload rejects files with disallowed mime types."""
    app = _create_app(mock_settings)

    with (
        patch(
            "loom.security.auth.get_settings",
            return_value=mock_settings,
        ),
        patch(
            f"{_SVC}.check_case_access",
            new_callable=AsyncMock,
            return_value=True,
        ),
        patch(
            f"{_SVC}.validate_file_type",
            side_effect=ValueError("not allowed"),
        ),
    ):
        token = create_access_token(str(_USER_ID), "analyst")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            resp = await ac.post(
                f"/api/v1/cases/{_CASE_ID}/assets/upload",
                files={
                    "file": (
                        "malware.exe",
                        b"\x7fELF" + b"\x00" * 100,
                        "application/octet-stream",
                    )
                },
                headers=_auth_header(token),
            )

    assert resp.status_code == 415


async def test_list_assets(
    mock_settings: Settings,
) -> None:
    """list assets returns uploaded items."""
    app = _create_app(mock_settings)
    asset = _make_asset()

    # mock db execute for count and select
    mock_count_result = MagicMock()
    mock_count_result.scalar_one.return_value = 1

    mock_scalars = MagicMock()
    mock_scalars.all.return_value = [asset]
    mock_select_result = MagicMock()
    mock_select_result.scalars.return_value = mock_scalars

    async def _override_db():
        stub = _StubSession()
        results = [mock_count_result, mock_select_result]
        idx = {"val": 0}

        async def _execute(stmt):
            r = results[idx["val"]]
            idx["val"] += 1
            return r

        stub.execute = _execute  # type: ignore[assignment]
        yield stub

    app.dependency_overrides[get_db_session] = _override_db

    with (
        patch(
            "loom.security.auth.get_settings",
            return_value=mock_settings,
        ),
        patch(
            f"{_SVC}.check_case_access",
            new_callable=AsyncMock,
            return_value=True,
        ),
        patch(
            "loom.schemas.asset.AssetResponse.model_validate",
            side_effect=lambda a: _asset_response_from_mock(a),
        ),
    ):
        token = create_access_token(str(_USER_ID), "analyst")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            resp = await ac.get(
                f"/api/v1/cases/{_CASE_ID}/assets",
                headers=_auth_header(token),
            )

    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert len(data["items"]) == 1
    assert data["items"][0]["original_filename"] == "test.jpg"


def _asset_response_from_mock(a: MagicMock) -> dict:
    """convert mock asset to dict matching AssetResponse."""
    from loom.schemas.asset import AssetResponse

    return AssetResponse(
        id=a.id,
        case_id=a.case_id,
        original_filename=a.original_filename,
        storage_key=a.storage_key,
        media_type=a.media_type,
        mime_type=a.mime_type,
        file_size_bytes=a.file_size_bytes,
        sha256_hash=a.sha256_hash,
        sha512_hash=a.sha512_hash,
        upload_status=a.upload_status,
        uploaded_by=a.uploaded_by,
        uploaded_at=a.uploaded_at,
        metadata_raw=a.metadata_raw,
        metadata_extracted=a.metadata_extracted,
        capture_time=a.capture_time,
        capture_location_lat=a.capture_location_lat,
        capture_location_lon=a.capture_location_lon,
        processing_status=a.processing_status,
        created_at=a.created_at,
        updated_at=a.updated_at,
    )


async def test_get_asset_detail(
    mock_settings: Settings,
) -> None:
    """get asset returns correct detail."""
    app = _create_app(mock_settings)
    asset = _make_asset()

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = asset

    async def _override_db():
        stub = _StubSession()
        stub.execute = AsyncMock(return_value=mock_result)
        yield stub

    app.dependency_overrides[get_db_session] = _override_db

    with (
        patch(
            "loom.security.auth.get_settings",
            return_value=mock_settings,
        ),
        patch(
            f"{_SVC}.check_case_access",
            new_callable=AsyncMock,
            return_value=True,
        ),
        patch(
            "loom.schemas.asset.AssetResponse.model_validate",
            side_effect=lambda a: _asset_response_from_mock(a),
        ),
    ):
        token = create_access_token(str(_USER_ID), "analyst")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            resp = await ac.get(
                f"/api/v1/cases/{_CASE_ID}/assets/{_ASSET_ID}",
                headers=_auth_header(token),
            )

    assert resp.status_code == 200
    data = resp.json()
    assert data["original_filename"] == "test.jpg"
    assert data["sha256_hash"] == "a" * 64


async def test_download_url(
    mock_settings: Settings,
) -> None:
    """download url returns presigned url."""
    app = _create_app(mock_settings)
    asset = _make_asset()

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = asset

    async def _override_db():
        stub = _StubSession()
        stub.execute = AsyncMock(return_value=mock_result)
        yield stub

    app.dependency_overrides[get_db_session] = _override_db

    mock_minio = MagicMock()
    mock_minio.presigned_get_object.return_value = (
        "https://minio.local/download"
    )
    app.dependency_overrides[get_minio_client] = lambda: mock_minio

    with (
        patch(
            "loom.security.auth.get_settings",
            return_value=mock_settings,
        ),
        patch(
            f"{_SVC}.check_case_access",
            new_callable=AsyncMock,
            return_value=True,
        ),
    ):
        token = create_access_token(str(_USER_ID), "analyst")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            resp = await ac.get(
                f"/api/v1/cases/{_CASE_ID}/assets/{_ASSET_ID}/download-url",
                headers=_auth_header(token),
            )

    assert resp.status_code == 200
    data = resp.json()
    assert "url" in data
    assert "key" in data
