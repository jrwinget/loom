"""real-SQL coverage for the bootstrap-admin -> login round-trip.

the desktop flow auto-issues tokens from ``/first-run/complete``, so the
email+password verify path is exercised for the FIRST time only after a
restart -- which is exactly when "invalid email or password" surfaced on
an admin that had just been created. the unit tests never caught it
because they mock the session and never compile the email lookup.

this boots a real on-disk sqlite db the way the sidecar does, creates an
admin, and then logs in the way the login screen does: same creds, and
with differently-cased email (addresses are case-insensitive). it also
inserts a legacy mixed-case row directly to prove the case-insensitive
query matches an admin stored before email normalization landed -- i.e.
the already-stuck operator needs no factory reset.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import loom.config
from loom.models.user import User
from loom.security.auth import hash_password
from loom.security.rate_limit import limiter


@pytest.fixture(autouse=True)
def _reset_rate_limiter() -> None:
    """login is capped at 5/minute; clear the process-wide limiter so
    the multi-attempt cases hit the handler rather than a 429."""
    limiter.reset()


@pytest.fixture
def lite_env(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Path:
    """point the process at a fresh lite sqlite db and bootstrap it."""
    db_path = tmp_path / "loom.db"
    monkeypatch.setenv("LOOM_DEPLOYMENT_PROFILE", "lite")
    monkeypatch.setenv("LOOM_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("LOOM_DATABASE_URL", f"sqlite+aiosqlite:///{db_path}")
    monkeypatch.setenv("LOOM_SECRET_KEY", "x" * 48)
    monkeypatch.setenv("LOOM_STORAGE_SIGNING_SECRET", "y" * 48)

    loom.config.get_settings.cache_clear()
    from loom.__main__ import bootstrap_schema_if_lite

    bootstrap_schema_if_lite()
    yield db_path
    loom.config.get_settings.cache_clear()


@pytest_asyncio.fixture
async def lite_client(
    lite_env: Path,
) -> AsyncIterator[httpx.AsyncClient]:
    """yield a client served through the app lifespan so that
    app.state.db_session_factory points at the bootstrapped db."""
    from loom.main import create_app

    app = create_app()
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac,
    ):
        yield ac


_PASSWORD = "correct-horse-battery"
_ADMIN = {
    "admin_email": "Ada.Admin@Example.com",
    "admin_password": _PASSWORD,
    "admin_full_name": "Ada Admin",
}


@pytest.mark.asyncio
async def test_login_succeeds_after_bootstrap(
    lite_client: httpx.AsyncClient,
) -> None:
    """the admin created at first-run can sign in with those creds."""
    create = await lite_client.post("/api/v1/first-run/complete", json=_ADMIN)
    assert create.status_code == 201, create.text

    resp = await lite_client.post(
        "/api/v1/auth/login",
        json={"email": _ADMIN["admin_email"], "password": _PASSWORD},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["access_token"]


@pytest.mark.asyncio
async def test_login_is_case_insensitive(
    lite_client: httpx.AsyncClient,
) -> None:
    """email casing must not matter -- the original cause of the
    "invalid email or password" report on a restart."""
    await lite_client.post("/api/v1/first-run/complete", json=_ADMIN)

    for variant in (
        "ada.admin@example.com",
        "ADA.ADMIN@EXAMPLE.COM",
        "Ada.Admin@Example.com",
    ):
        resp = await lite_client.post(
            "/api/v1/auth/login",
            json={"email": variant, "password": _PASSWORD},
        )
        assert resp.status_code == 200, f"{variant}: {resp.text}"


@pytest.mark.asyncio
async def test_login_wrong_password_is_401(
    lite_client: httpx.AsyncClient,
) -> None:
    await lite_client.post("/api/v1/first-run/complete", json=_ADMIN)

    resp = await lite_client.post(
        "/api/v1/auth/login",
        json={"email": _ADMIN["admin_email"], "password": "wrong-password-xx"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_login_matches_legacy_mixed_case_row(
    lite_env: Path,
    lite_client: httpx.AsyncClient,
) -> None:
    """an admin stored with mixed-case email BEFORE normalization landed
    must still authenticate -- no factory reset for the stuck operator."""
    engine = create_async_engine(f"sqlite+aiosqlite:///{lite_env}")
    factory = async_sessionmaker(engine)
    async with factory() as session:
        session.add(
            User(
                email="Legacy.User@Example.com",
                display_name="Legacy User",
                role="admin",
                password_hash=hash_password(_PASSWORD),
            )
        )
        await session.commit()
    await engine.dispose()

    resp = await lite_client.post(
        "/api/v1/auth/login",
        json={"email": "legacy.user@example.com", "password": _PASSWORD},
    )
    assert resp.status_code == 200, resp.text


@pytest.mark.asyncio
async def test_me_includes_mfa_enabled(
    lite_client: httpx.AsyncClient,
) -> None:
    """/auth/me must emit mfa_enabled; the frontend User type reads it
    and it was previously absent from the response."""
    create = await lite_client.post("/api/v1/first-run/complete", json=_ADMIN)
    token = create.json()["access_token"]

    me = await lite_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert me.status_code == 200, me.text
    body = me.json()
    assert body["mfa_enabled"] is False
    # the stored email was normalized to lowercase on write.
    assert body["email"] == "ada.admin@example.com"
