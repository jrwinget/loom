"""real-SQL coverage for the capabilities endpoint (lite profile)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
import pytest_asyncio

import loom.config
from loom.security.rate_limit import limiter
from loom.workflows import shared

_ADMIN = {
    "admin_email": "admin@example.com",
    "admin_password": "correct-horse-battery",
    "admin_full_name": "Ada Admin",
}

_ENGINE_KEYS = {
    "transcription_local",
    "transcription_cloud",
    "ocr",
    "scene_detection",
    "media_pipeline",
    "diarization",
}


@pytest.fixture(autouse=True)
def _reset_rate_limiter() -> None:
    limiter.reset()


@pytest.fixture
def lite_env(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[Path]:
    db_path = tmp_path / "loom.db"
    monkeypatch.setenv("LOOM_DEPLOYMENT_PROFILE", "lite")
    monkeypatch.setenv("LOOM_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("LOOM_DATABASE_URL", f"sqlite+aiosqlite:///{db_path}")
    monkeypatch.setenv("LOOM_SECRET_KEY", "x" * 48)
    monkeypatch.setenv("LOOM_STORAGE_SIGNING_SECRET", "y" * 48)

    loom.config.get_settings.cache_clear()
    shared.reset_for_testing()
    from loom.__main__ import bootstrap_schema_if_lite

    bootstrap_schema_if_lite()
    yield db_path
    loom.config.get_settings.cache_clear()
    shared.reset_for_testing()


@pytest_asyncio.fixture
async def lite_client(
    lite_env: Path,
) -> AsyncIterator[httpx.AsyncClient]:
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


async def _admin_headers(ac: httpx.AsyncClient) -> dict[str, str]:
    resp = await ac.post("/api/v1/first-run/complete", json=_ADMIN)
    assert resp.status_code == 201, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


@pytest.mark.asyncio
async def test_capabilities_reports_profile_and_engines(
    lite_client: httpx.AsyncClient,
) -> None:
    headers = await _admin_headers(lite_client)

    resp = await lite_client.get("/api/v1/capabilities", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["profile"] == "lite"
    assert set(body["engines"].keys()) == _ENGINE_KEYS
    for state in body["engines"].values():
        assert state["status"] in ("available", "missing")
        if state["status"] == "missing":
            # a missing engine must always carry an actionable remedy
            assert state["remedy"]
    # cloud transcription is config-driven, never "missing"
    assert body["engines"]["transcription_cloud"]["status"] == "available"


@pytest.mark.asyncio
async def test_capabilities_requires_auth(
    lite_client: httpx.AsyncClient,
) -> None:
    resp = await lite_client.get("/api/v1/capabilities")
    assert resp.status_code in (401, 403)
