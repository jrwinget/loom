"""tests for the /first-run onboarding endpoints."""

from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock, patch
from uuid import UUID, uuid4

import httpx
import pytest_asyncio
from sqlalchemy import Select

from loom.config import Settings, get_settings
from loom.dependencies import get_db_session
from loom.models.user import User
from loom.security.auth import decode_token, verify_password


def _make_existing_user() -> MagicMock:
    user = MagicMock(spec=User)
    user.id = UUID("01912345-6789-7abc-8def-0123456789ab")
    user.email = "existing@example.com"
    user.display_name = "Existing"
    user.role = "admin"
    user.is_active = True
    user.password_hash = "hash"
    user.created_at = datetime(2025, 1, 1, tzinfo=UTC)
    user.updated_at = datetime(2025, 1, 1, tzinfo=UTC)
    return user


class _StatusSession:
    """mock async session that reports a fixed user count."""

    def __init__(self, *, user_count: int) -> None:
        self._user_count = user_count
        self.added: list[object] = []

    async def execute(self, stmt: Select[Any]) -> MagicMock:
        result = MagicMock()
        # count(*) query for User
        if "count" in str(stmt).lower():
            result.scalar_one.return_value = self._user_count
        else:
            result.scalar_one.return_value = self._user_count
        return result

    def add(self, obj: object) -> None:
        self.added.append(obj)
        # simulate DB-generated id + timestamps
        if isinstance(obj, User):
            if getattr(obj, "id", None) is None:
                obj.id = uuid4()
            obj.created_at = datetime.now(UTC)
            obj.updated_at = datetime.now(UTC)
            obj.is_active = True

    async def commit(self) -> None:
        return None

    async def refresh(self, obj: object) -> None:
        return None


@pytest_asyncio.fixture
def settings() -> Settings:
    return Settings(
        secret_key="test-secret-key-that-is-long-enough-for-validation",
        access_token_expire_minutes=15,
        refresh_token_expire_days=7,
        database_url="sqlite+aiosqlite:///",
    )


def _build_app(session: _StatusSession, cfg: Settings) -> Any:
    """build a FastAPI app wired to a mock db session."""
    get_settings.cache_clear()

    with patch("loom.config.get_settings", return_value=cfg):
        from loom.main import create_app

        application = create_app()

    async def override_db() -> Any:
        yield session

    application.dependency_overrides[get_db_session] = override_db
    # skip audit writes + revocation checks
    application.state.db_session_factory = None
    return application


async def test_status_returns_first_run_required_when_no_users(
    settings: Settings,
) -> None:
    """GET /first-run/status reports True when no users exist."""
    session = _StatusSession(user_count=0)
    app = _build_app(session, settings)

    with patch(
        "loom.api.v1.first_run.get_settings",
        return_value=settings,
    ):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            resp = await ac.get("/api/v1/first-run/status")

    assert resp.status_code == 200
    body = resp.json()
    assert body["first_run_required"] is True
    assert body["deployment_profile"] == "server"
    # server profile: data_dir should be null
    assert body["data_dir"] is None


async def test_status_returns_false_when_users_exist(
    settings: Settings,
) -> None:
    """GET /first-run/status reports False when a user exists."""
    session = _StatusSession(user_count=1)
    app = _build_app(session, settings)

    with patch(
        "loom.api.v1.first_run.get_settings",
        return_value=settings,
    ):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            resp = await ac.get("/api/v1/first-run/status")

    assert resp.status_code == 200
    body = resp.json()
    assert body["first_run_required"] is False


async def test_status_includes_data_dir_on_lite_profile(
    settings: Settings,
) -> None:
    """lite profile: data_dir is populated from settings."""
    lite_settings = Settings(
        secret_key=settings.secret_key,
        database_url="sqlite+aiosqlite:///:memory:",
        deployment_profile="lite",
    )
    session = _StatusSession(user_count=0)
    app = _build_app(session, settings)

    with patch(
        "loom.api.v1.first_run.get_settings",
        return_value=lite_settings,
    ):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            resp = await ac.get("/api/v1/first-run/status")

    body = resp.json()
    assert body["deployment_profile"] == "lite"
    assert isinstance(body["data_dir"], str)
    assert body["data_dir"].endswith("data") or "/.loom/" in body["data_dir"]


async def test_complete_creates_admin_and_returns_tokens(
    settings: Settings,
) -> None:
    """POST /first-run/complete succeeds when no users exist."""
    session = _StatusSession(user_count=0)
    app = _build_app(session, settings)

    payload = {
        "admin_email": "admin@example.com",
        "admin_password": "supersecret-password-12",
        "admin_full_name": "Admin Example",
    }

    with patch(
        "loom.security.auth.get_settings",
        return_value=settings,
    ):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            resp = await ac.post(
                "/api/v1/first-run/complete",
                json=payload,
            )

    assert resp.status_code == 201
    body = resp.json()
    assert "user_id" in body
    assert body["token_type"] == "bearer"
    assert body["access_token"]
    assert body["refresh_token"]

    # admin user was persisted with role=admin and hashed password
    assert len(session.added) == 1
    created = session.added[0]
    assert isinstance(created, User)
    assert created.email == payload["admin_email"]
    assert created.display_name == payload["admin_full_name"]
    assert created.role == "admin"
    # password must be hashed, not stored plaintext
    assert created.password_hash != payload["admin_password"]
    assert verify_password(payload["admin_password"], created.password_hash)

    # access token encodes the user's role
    with patch(
        "loom.security.auth.get_settings",
        return_value=settings,
    ):
        decoded = decode_token(body["access_token"])
    assert decoded["role"] == "admin"


async def test_complete_returns_409_when_user_already_exists(
    settings: Settings,
) -> None:
    """POST /first-run/complete returns 409 if any user exists."""
    session = _StatusSession(user_count=1)
    app = _build_app(session, settings)

    payload = {
        "admin_email": "admin@example.com",
        "admin_password": "supersecret-password-12",
        "admin_full_name": "Admin Example",
    }

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as ac:
        resp = await ac.post(
            "/api/v1/first-run/complete",
            json=payload,
        )

    assert resp.status_code == 409
    assert session.added == []


async def test_complete_rejects_short_password(
    settings: Settings,
) -> None:
    """POST /first-run/complete rejects passwords under 12 chars."""
    session = _StatusSession(user_count=0)
    app = _build_app(session, settings)

    payload = {
        "admin_email": "admin@example.com",
        "admin_password": "short",
        "admin_full_name": "Admin Example",
    }

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as ac:
        resp = await ac.post(
            "/api/v1/first-run/complete",
            json=payload,
        )

    assert resp.status_code == 422
    assert session.added == []
