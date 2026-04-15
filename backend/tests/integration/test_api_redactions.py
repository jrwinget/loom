"""integration tests for redaction api endpoints."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import httpx
import pytest

from loom.config import Settings, get_settings
from loom.dependencies import get_db_session
from loom.models.redaction import Redaction
from loom.security.auth import create_access_token

_ADMIN_ID = UUID("01912345-6789-7abc-8def-0123456789ab")
_USER_ID = UUID("01912345-6789-7abc-8def-0123456789cd")
_CASE_ID = UUID("01912345-6789-7abc-8def-0123456789ef")
_ASSET_ID = UUID("01912345-6789-7abc-8def-012345678901")
_REDACTION_ID = UUID("01912345-6789-7abc-8def-012345678902")
_NOW = datetime(2025, 1, 1, tzinfo=UTC)

_SVC = "loom.api.v1.redactions"


class _StubSession:
    async def execute(self, stmt):  # type: ignore[no-untyped-def]
        return MagicMock()

    def add(self, obj):  # type: ignore[no-untyped-def]
        pass

    async def flush(self) -> None:
        pass

    async def commit(self) -> None:
        pass

    async def refresh(self, obj) -> None:  # type: ignore[no-untyped-def]
        pass


def _create_app(settings: Settings) -> object:
    get_settings.cache_clear()
    with patch("loom.config.get_settings", return_value=settings):
        from loom.main import create_app

        application = create_app()

    async def override_db():  # type: ignore[no-untyped-def]
        yield _StubSession()

    application.dependency_overrides[get_db_session] = override_db
    application.state.db_session_factory = None
    application.state.minio_client = MagicMock()
    return application


@pytest.fixture
def mock_settings() -> Settings:
    return Settings(
        secret_key=("test-secret-key-that-is-long-enough-for-validation"),
        database_url="sqlite+aiosqlite:///",
    )


def _auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _make_redaction(
    *,
    status: str = "pending",
) -> MagicMock:
    r = MagicMock(spec=Redaction)
    r.id = _REDACTION_ID
    r.asset_id = _ASSET_ID
    r.redacted_by = _USER_ID
    r.redaction_type = "blur"
    r.regions = [
        {
            "type": "rect",
            "x": 0.1,
            "y": 0.1,
            "w": 0.3,
            "h": 0.3,
        }
    ]
    r.status = status
    r.output_storage_key = None
    r.error_message = None
    r.created_at = _NOW
    r.updated_at = _NOW
    return r


async def test_create_redaction(
    mock_settings: Settings,
) -> None:
    """editor can create a redaction."""
    app = _create_app(mock_settings)
    redaction = _make_redaction()

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
            f"{_SVC}.create_redaction",
            new_callable=AsyncMock,
            return_value=redaction,
        ),
    ):
        token = create_access_token(str(_USER_ID), "analyst")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            resp = await ac.post(
                f"/api/v1/cases/{_CASE_ID}/assets/{_ASSET_ID}/redactions",
                json={
                    "redaction_type": "blur",
                    "regions": [
                        {
                            "type": "rect",
                            "x": 0.1,
                            "y": 0.1,
                            "w": 0.3,
                            "h": 0.3,
                        }
                    ],
                },
                headers=_auth_header(token),
            )

    assert resp.status_code == 201
    data = resp.json()
    assert data["redaction_type"] == "blur"
    assert data["status"] == "pending"


async def test_create_redaction_forbidden(
    mock_settings: Settings,
) -> None:
    """non-editor cannot create redaction."""
    app = _create_app(mock_settings)

    with (
        patch(
            "loom.security.auth.get_settings",
            return_value=mock_settings,
        ),
        patch(
            f"{_SVC}.check_case_access",
            new_callable=AsyncMock,
            return_value=False,
        ),
    ):
        token = create_access_token(str(_USER_ID), "analyst")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            resp = await ac.post(
                f"/api/v1/cases/{_CASE_ID}/assets/{_ASSET_ID}/redactions",
                json={
                    "redaction_type": "blur",
                    "regions": [
                        {
                            "type": "rect",
                            "x": 0.1,
                            "y": 0.1,
                            "w": 0.3,
                            "h": 0.3,
                        }
                    ],
                },
                headers=_auth_header(token),
            )

    assert resp.status_code == 403


async def test_list_redactions(
    mock_settings: Settings,
) -> None:
    """viewer can list redactions."""
    app = _create_app(mock_settings)
    redaction = _make_redaction()

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
            f"{_SVC}.get_redactions",
            new_callable=AsyncMock,
            return_value=([redaction], 1),
        ),
    ):
        token = create_access_token(str(_USER_ID), "analyst")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            resp = await ac.get(
                f"/api/v1/cases/{_CASE_ID}/assets/{_ASSET_ID}/redactions",
                headers=_auth_header(token),
            )

    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["redaction_type"] == "blur"


async def test_get_single_redaction(
    mock_settings: Settings,
) -> None:
    """get a single redaction by id."""
    app = _create_app(mock_settings)
    redaction = _make_redaction()

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
            f"{_SVC}.get_redaction",
            new_callable=AsyncMock,
            return_value=redaction,
        ),
    ):
        token = create_access_token(str(_USER_ID), "analyst")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            resp = await ac.get(
                f"/api/v1/cases/{_CASE_ID}/assets/"
                f"{_ASSET_ID}/redactions/{_REDACTION_ID}",
                headers=_auth_header(token),
            )

    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == str(_REDACTION_ID)


async def test_get_redaction_not_found(
    mock_settings: Settings,
) -> None:
    """missing redaction returns 404."""
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
            f"{_SVC}.get_redaction",
            new_callable=AsyncMock,
            return_value=None,
        ),
    ):
        token = create_access_token(str(_USER_ID), "analyst")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            resp = await ac.get(
                f"/api/v1/cases/{_CASE_ID}/assets/"
                f"{_ASSET_ID}/redactions/{_REDACTION_ID}",
                headers=_auth_header(token),
            )

    assert resp.status_code == 404


async def test_apply_redaction(
    mock_settings: Settings,
) -> None:
    """editor can apply a redaction."""
    app = _create_app(mock_settings)
    redaction = _make_redaction(status="pending")
    applied = _make_redaction(status="complete")

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
            f"{_SVC}.get_redaction",
            new_callable=AsyncMock,
            return_value=redaction,
        ),
        patch(
            f"{_SVC}.apply_redaction",
            new_callable=AsyncMock,
            return_value=applied,
        ),
        patch(
            "loom.services.storage.StorageService.get_object_stream",
            return_value=(4, iter([b"fake"])),
        ),
    ):
        token = create_access_token(str(_USER_ID), "analyst")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            resp = await ac.post(
                f"/api/v1/cases/{_CASE_ID}/assets/"
                f"{_ASSET_ID}/redactions/"
                f"{_REDACTION_ID}/apply",
                headers=_auth_header(token),
            )

    assert resp.status_code == 202
    data = resp.json()
    assert data["status"] == "complete"


async def test_apply_redaction_not_found(
    mock_settings: Settings,
) -> None:
    """applying missing redaction returns 404."""
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
            f"{_SVC}.get_redaction",
            new_callable=AsyncMock,
            return_value=None,
        ),
    ):
        token = create_access_token(str(_USER_ID), "analyst")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            resp = await ac.post(
                f"/api/v1/cases/{_CASE_ID}/assets/"
                f"{_ASSET_ID}/redactions/"
                f"{_REDACTION_ID}/apply",
                headers=_auth_header(token),
            )

    assert resp.status_code == 404


async def test_create_redaction_invalid_body(
    mock_settings: Settings,
) -> None:
    """empty regions list returns 422."""
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
    ):
        token = create_access_token(str(_USER_ID), "analyst")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            resp = await ac.post(
                f"/api/v1/cases/{_CASE_ID}/assets/{_ASSET_ID}/redactions",
                json={
                    "redaction_type": "blur",
                    "regions": [],
                },
                headers=_auth_header(token),
            )

    assert resp.status_code == 422
