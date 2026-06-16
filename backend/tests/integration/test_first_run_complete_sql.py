"""real-SQL coverage for the first-run bootstrap flow (lite profile).

the unit tests in ``test_first_run_api.py`` drive ``/first-run/complete``
against a mock session that hard-codes ``rowcount``, so they cannot see
how the atomic ``INSERT ... WHERE NOT EXISTS`` actually compiles. a
double-wrapped ``exists()`` once made that guard always-true, inserting
zero rows on every install and pinning the desktop shell in a
first-run -> "already set up" -> login -> first-run loop.

this test exercises the endpoint against a real on-disk sqlite database
booted exactly the way the tauri sidecar boots it: schema materialised
by ``bootstrap_schema_if_lite``, app served through its lifespan. it
fails loudly if the insert ever stops inserting on an empty table.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
import pytest_asyncio

import loom.config
from loom.security.rate_limit import limiter


@pytest.fixture(autouse=True)
def _reset_rate_limiter() -> None:
    """clear the in-memory rate limiter between tests.

    /first-run/complete is capped at 3/minute and the limiter is a
    process-wide singleton keyed by client ip; without a reset the
    later cases would 429 instead of exercising the real handler.
    """
    limiter.reset()


@pytest.fixture
def lite_env(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Path:
    """point the process at a fresh lite sqlite db and bootstrap it.

    runs in a sync fixture because ``bootstrap_schema_if_lite`` drives
    ``asyncio.run`` internally (it is built for the sidecar's sync
    ``main()``); calling it from inside pytest-asyncio's running loop
    would raise "asyncio.run() cannot be called from a running event
    loop".
    """
    db_path = tmp_path / "loom.db"
    monkeypatch.setenv("LOOM_DEPLOYMENT_PROFILE", "lite")
    monkeypatch.setenv("LOOM_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("LOOM_DATABASE_URL", f"sqlite+aiosqlite:///{db_path}")
    monkeypatch.setenv("LOOM_SECRET_KEY", "x" * 48)
    monkeypatch.setenv("LOOM_STORAGE_SIGNING_SECRET", "y" * 48)

    # get_settings is lru_cached and read by every caller; clear it so
    # the env above takes effect, and again on teardown so a lite
    # config does not leak into other tests sharing the process.
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


_ADMIN = {
    "admin_email": "admin@example.com",
    "admin_password": "correct-horse-battery",
    "admin_full_name": "Ada Admin",
}


@pytest.mark.asyncio
async def test_complete_inserts_admin_on_empty_db(
    lite_client: httpx.AsyncClient,
) -> None:
    """a fresh install must accept the bootstrap admin (201, not 409)."""
    status = await lite_client.get("/api/v1/first-run/status")
    assert status.status_code == 200
    assert status.json()["first_run_required"] is True

    resp = await lite_client.post("/api/v1/first-run/complete", json=_ADMIN)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["access_token"]
    assert body["refresh_token"]
    assert len(body["password_recovery_codes"]) == 8


@pytest.mark.asyncio
async def test_status_flips_after_complete(
    lite_client: httpx.AsyncClient,
) -> None:
    """once an admin exists /status stops demanding onboarding, so the
    login page no longer bounces the operator back into first-run."""
    await lite_client.post("/api/v1/first-run/complete", json=_ADMIN)

    status = await lite_client.get("/api/v1/first-run/status")
    assert status.status_code == 200
    assert status.json()["first_run_required"] is False


@pytest.mark.asyncio
async def test_complete_is_single_shot(
    lite_client: httpx.AsyncClient,
) -> None:
    """the TOCTOU guard still rejects a second bootstrap with 409."""
    first = await lite_client.post("/api/v1/first-run/complete", json=_ADMIN)
    assert first.status_code == 201, first.text

    second = await lite_client.post("/api/v1/first-run/complete", json=_ADMIN)
    assert second.status_code == 409
    assert "already completed" in second.json()["detail"]
