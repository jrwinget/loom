"""integration tests for /api/v1/storage endpoints (issue #47).

covers the lite-only gate, auth + admin enforcement, the pre-ingest
check path, and the happy-path shape of /usage and /relocate. the
actual relocation is unit-tested in test_storage_relocation.py; these
tests just assert the endpoint wiring.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch
from uuid import UUID

import httpx
import pytest_asyncio

from loom.config import Settings, get_settings
from loom.dependencies import get_db_session
from loom.security.auth import create_access_token
from loom.security.rate_limit import limiter
from loom.services.storage_relocation import (
    RELOCATION_REGISTRY,
    RelocationJob,
)

_ADMIN_ID = UUID("01912345-6789-7abc-8def-0123456789ab")
_ANALYST_ID = UUID("01912345-6789-7abc-8def-0123456789cd")


class _StubSession:
    """minimal stub for dependency override on endpoints that query."""

    async def execute(self, stmt):  # type: ignore[no-untyped-def]
        # /usage counts assets via select(func.count()); return 0.
        result = MagicMock()
        result.scalar_one.return_value = 0
        return result

    def add(self, obj):  # type: ignore[no-untyped-def]
        pass

    async def flush(self) -> None:
        pass

    async def commit(self) -> None:
        pass


def _create_app(settings: Settings) -> object:
    """build a test app with stub session + null session factory."""
    get_settings.cache_clear()
    with patch("loom.config.get_settings", return_value=settings):
        from loom.main import create_app

        application = create_app()

    async def override_db():  # type: ignore[no-untyped-def]
        yield _StubSession()

    application.dependency_overrides[get_db_session] = override_db
    application.state.db_session_factory = None
    return application


def _lite_settings(tmp_path: Path) -> Settings:
    return Settings(
        secret_key=("test-secret-key-that-is-long-enough-for-validation"),
        deployment_profile="lite",
        data_dir=tmp_path,
        database_url="sqlite+aiosqlite:///",
        storage_signing_secret="unit-test-signing-secret",
    )


def _server_settings() -> Settings:
    return Settings(
        secret_key=("test-secret-key-that-is-long-enough-for-validation"),
        deployment_profile="server",
        database_url="sqlite+aiosqlite:///",
    )


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture(autouse=True)
def _scrub_registry():
    # clear both the relocation registry and slowapi state so each
    # test starts with a clean /relocate rate budget.
    RELOCATION_REGISTRY.clear()
    limiter.reset()
    yield
    RELOCATION_REGISTRY.clear()
    limiter.reset()


# ---------------------------------------------------------------------
# /storage/usage
# ---------------------------------------------------------------------


async def test_usage_lite_returns_breakdown(tmp_path: Path) -> None:
    """lite profile returns the full usage envelope."""
    settings = _lite_settings(tmp_path)
    app = _create_app(settings)

    with (
        patch("loom.security.auth.get_settings", return_value=settings),
        patch("loom.api.v1.storage.get_settings", return_value=settings),
    ):
        token = create_access_token(str(_ADMIN_ID), "admin")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            resp = await ac.get("/api/v1/storage/usage", headers=_auth(token))

    assert resp.status_code == 200
    body = resp.json()
    assert body["data_dir"] == str(tmp_path.resolve())
    assert body["asset_count"] == 0
    assert body["free_bytes"] >= 0
    assert body["total_bytes"] >= 0
    assert body["on_system_drive"] in (True, False)


async def test_usage_server_profile_404s(tmp_path: Path) -> None:
    """server profile refuses the endpoint with 404."""
    settings = _server_settings()
    app = _create_app(settings)

    with (
        patch("loom.security.auth.get_settings", return_value=settings),
        patch("loom.api.v1.storage.get_settings", return_value=settings),
    ):
        token = create_access_token(str(_ADMIN_ID), "admin")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            resp = await ac.get("/api/v1/storage/usage", headers=_auth(token))

    assert resp.status_code == 404
    assert "Lite profile" in resp.json()["detail"]


async def test_usage_requires_auth(tmp_path: Path) -> None:
    """no token → 401/403."""
    settings = _lite_settings(tmp_path)
    app = _create_app(settings)
    with (
        patch("loom.security.auth.get_settings", return_value=settings),
        patch("loom.api.v1.storage.get_settings", return_value=settings),
    ):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            resp = await ac.get("/api/v1/storage/usage")
    assert resp.status_code in (401, 403)


# ---------------------------------------------------------------------
# /storage/check
# ---------------------------------------------------------------------


async def test_check_writable_returns_proceed(tmp_path: Path) -> None:
    """a writable tmp path with a tiny batch comes back proceed."""
    settings = _lite_settings(tmp_path)
    app = _create_app(settings)

    with (
        patch("loom.security.auth.get_settings", return_value=settings),
        patch("loom.api.v1.storage.get_settings", return_value=settings),
    ):
        token = create_access_token(str(_ADMIN_ID), "admin")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            resp = await ac.post(
                "/api/v1/storage/check",
                json={"path": str(tmp_path), "estimated_batch_size": 1024},
                headers=_auth(token),
            )

    assert resp.status_code == 200
    body = resp.json()
    assert body["writable"] is True
    assert body["advisory"] == "proceed"


async def test_check_blocked_for_cloud_sync(tmp_path: Path) -> None:
    """cloud-sync path comes back blocked + unwritable."""
    settings = _lite_settings(tmp_path)
    app = _create_app(settings)
    fake = tmp_path / "OneDrive" / "loom"

    with (
        patch("loom.security.auth.get_settings", return_value=settings),
        patch("loom.api.v1.storage.get_settings", return_value=settings),
    ):
        token = create_access_token(str(_ADMIN_ID), "admin")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            resp = await ac.post(
                "/api/v1/storage/check",
                json={"path": str(fake), "estimated_batch_size": 0},
                headers=_auth(token),
            )

    assert resp.status_code == 200
    body = resp.json()
    assert body["writable"] is False
    assert body["advisory"] == "blocked"
    assert "cloud-sync" in (body["advisory_reason"] or "").lower()


# ---------------------------------------------------------------------
# /storage/relocate
# ---------------------------------------------------------------------


async def test_relocate_rejects_non_admin(tmp_path: Path) -> None:
    """analysts can't trigger a data-dir move."""
    settings = _lite_settings(tmp_path)
    app = _create_app(settings)

    with (
        patch("loom.security.auth.get_settings", return_value=settings),
        patch("loom.api.v1.storage.get_settings", return_value=settings),
    ):
        token = create_access_token(str(_ANALYST_ID), "analyst")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            resp = await ac.post(
                "/api/v1/storage/relocate",
                json={"target_path": str(tmp_path / "elsewhere")},
                headers=_auth(token),
            )

    assert resp.status_code == 403
    assert "admin" in resp.json()["detail"].lower()


async def test_relocate_server_profile_404s(tmp_path: Path) -> None:
    """server profile refuses relocate regardless of role."""
    settings = _server_settings()
    app = _create_app(settings)

    with (
        patch("loom.security.auth.get_settings", return_value=settings),
        patch("loom.api.v1.storage.get_settings", return_value=settings),
    ):
        token = create_access_token(str(_ADMIN_ID), "admin")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            resp = await ac.post(
                "/api/v1/storage/relocate",
                json={"target_path": str(tmp_path)},
                headers=_auth(token),
            )

    assert resp.status_code == 404


async def test_relocate_returns_202_with_job_id(tmp_path: Path) -> None:
    """admin kicks off a job and gets a job id back."""
    settings = _lite_settings(tmp_path)
    app = _create_app(settings)
    dst = tmp_path.parent / f"{tmp_path.name}-dst"

    fake_job = RelocationJob(
        job_id="abc",
        src=tmp_path,
        dst=dst,
        status="running",
    )
    with (
        patch("loom.security.auth.get_settings", return_value=settings),
        patch("loom.api.v1.storage.get_settings", return_value=settings),
        patch(
            "loom.api.v1.storage.start_relocation",
            return_value=fake_job,
        ),
    ):
        token = create_access_token(str(_ADMIN_ID), "admin")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            resp = await ac.post(
                "/api/v1/storage/relocate",
                json={"target_path": str(dst)},
                headers=_auth(token),
            )

    assert resp.status_code == 202
    assert resp.json() == {"job_id": "abc"}


async def test_relocate_surfaces_validation_errors(tmp_path: Path) -> None:
    """service-layer ValueError becomes a 400 with the reason."""
    settings = _lite_settings(tmp_path)
    app = _create_app(settings)

    err = ValueError("destination path is inside the current data dir")
    with (
        patch("loom.security.auth.get_settings", return_value=settings),
        patch("loom.api.v1.storage.get_settings", return_value=settings),
        patch(
            "loom.api.v1.storage.start_relocation",
            side_effect=err,
        ),
    ):
        token = create_access_token(str(_ADMIN_ID), "admin")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            resp = await ac.post(
                "/api/v1/storage/relocate",
                json={"target_path": str(tmp_path / "child")},
                headers=_auth(token),
            )

    assert resp.status_code == 400
    assert "inside" in resp.json()["detail"]


# ---------------------------------------------------------------------
# /storage/relocate/{job_id}
# ---------------------------------------------------------------------


async def test_relocate_status_returns_job_snapshot(tmp_path: Path) -> None:
    """polling an existing job returns its current counters."""
    settings = _lite_settings(tmp_path)
    app = _create_app(settings)

    job = RelocationJob(
        job_id="poll-me",
        src=tmp_path,
        dst=tmp_path.parent,
        status="completed",
        assets_copied=5,
        assets_total=5,
        bytes_copied=1000,
        bytes_total=1000,
    )
    RELOCATION_REGISTRY["poll-me"] = job

    with (
        patch("loom.security.auth.get_settings", return_value=settings),
        patch("loom.api.v1.storage.get_settings", return_value=settings),
    ):
        token = create_access_token(str(_ADMIN_ID), "admin")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            resp = await ac.get(
                "/api/v1/storage/relocate/poll-me",
                headers=_auth(token),
            )

    assert resp.status_code == 200
    body = resp.json()
    assert body["job_id"] == "poll-me"
    assert body["status"] == "completed"
    assert body["assets_copied"] == 5


async def test_relocate_status_unknown_job_404s(tmp_path: Path) -> None:
    """unknown job id returns 404."""
    settings = _lite_settings(tmp_path)
    app = _create_app(settings)

    with (
        patch("loom.security.auth.get_settings", return_value=settings),
        patch("loom.api.v1.storage.get_settings", return_value=settings),
    ):
        token = create_access_token(str(_ADMIN_ID), "admin")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            resp = await ac.get(
                "/api/v1/storage/relocate/nope",
                headers=_auth(token),
            )

    assert resp.status_code == 404
