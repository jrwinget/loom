"""real-SQL coverage for the engines/model-management endpoints.

boots a lite sqlite db the way the sidecar does and exercises the
status/download/delete surface with a real app, real auth, and a
faked registry download (the pinned manifests point at real
hundred-megabyte weights; the download mechanics themselves are
unit-tested against a mock transport in test_model_registry.py).
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
import pytest_asyncio

import loom.config
from loom.security.auth import create_access_token
from loom.security.rate_limit import limiter


@pytest.fixture(autouse=True)
def _reset_rate_limiter() -> None:
    limiter.reset()


@pytest.fixture(autouse=True)
def _reset_download_state() -> None:
    from loom.api.v1 import engines

    engines._DOWNLOADS.clear()
    engines._TASKS.clear()


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
    from loom.__main__ import bootstrap_schema_if_lite

    bootstrap_schema_if_lite()
    yield tmp_path
    loom.config.get_settings.cache_clear()


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


async def _admin_headers(client: httpx.AsyncClient) -> dict[str, str]:
    resp = await client.post(
        "/api/v1/first-run/complete",
        json={
            "admin_email": "ada@example.org",
            "admin_password": "correct-horse-battery",
            "admin_full_name": "Ada Admin",
        },
    )
    assert resp.status_code == 201, resp.text
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _viewer_headers() -> dict[str, str]:
    token = create_access_token(
        "11111111-2222-7333-8444-555555555555", "viewer"
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_engine_status_lists_catalog(
    lite_client: httpx.AsyncClient,
) -> None:
    headers = await _admin_headers(lite_client)
    resp = await lite_client.get("/api/v1/settings/engines", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert "transcription_local" in body["engines"]
    names = {m["name"] for m in body["models"]}
    assert names == {"tiny", "base", "small"}
    for model in body["models"]:
        assert model["downloaded"] is False
        assert model["size_bytes"] > 0


@pytest.mark.asyncio
async def test_download_lifecycle(
    lite_client: httpx.AsyncClient,
    lite_env: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers = await _admin_headers(lite_client)

    installed = lite_env / "models" / "whisper" / "tiny"

    async def fake_download(name: str, **kwargs: object) -> Path:
        on_progress = kwargs.get("on_progress")
        if callable(on_progress):
            on_progress(10, 10)
        installed.mkdir(parents=True, exist_ok=True)
        return installed

    monkeypatch.setattr(
        "loom.services.model_registry.download_model", fake_download
    )

    resp = await lite_client.post(
        "/api/v1/settings/engines/models/tiny/download", headers=headers
    )
    assert resp.status_code == 202, resp.text
    assert resp.json()["download_status"] == "downloading"

    # let the fire-and-forget task run on this loop
    await asyncio.sleep(0)

    status = await lite_client.get(
        "/api/v1/settings/engines/models/tiny/status", headers=headers
    )
    body = status.json()
    assert body["download_status"] == "complete"
    assert body["bytes_done"] == 10

    delete = await lite_client.delete(
        "/api/v1/settings/engines/models/tiny", headers=headers
    )
    assert delete.status_code == 204
    assert not installed.exists()


@pytest.mark.asyncio
async def test_download_failure_is_reported(
    lite_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers = await _admin_headers(lite_client)

    async def failing_download(name: str, **kwargs: object) -> Path:
        raise RuntimeError("network unreachable")

    monkeypatch.setattr(
        "loom.services.model_registry.download_model", failing_download
    )

    resp = await lite_client.post(
        "/api/v1/settings/engines/models/base/download", headers=headers
    )
    assert resp.status_code == 202
    await asyncio.sleep(0)

    status = await lite_client.get(
        "/api/v1/settings/engines/models/base/status", headers=headers
    )
    body = status.json()
    assert body["download_status"] == "failed"
    assert "network unreachable" in body["error"]


@pytest.mark.asyncio
async def test_unknown_model_404(lite_client: httpx.AsyncClient) -> None:
    headers = await _admin_headers(lite_client)
    resp = await lite_client.post(
        "/api/v1/settings/engines/models/gigantic/download", headers=headers
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_mutations_require_admin(
    lite_client: httpx.AsyncClient,
) -> None:
    # the admin must exist so auth middleware has a live install
    await _admin_headers(lite_client)
    viewer = _viewer_headers()

    resp = await lite_client.post(
        "/api/v1/settings/engines/models/tiny/download", headers=viewer
    )
    assert resp.status_code == 403

    resp = await lite_client.delete(
        "/api/v1/settings/engines/models/tiny", headers=viewer
    )
    assert resp.status_code == 403

    # read-only status stays viewer-accessible
    resp = await lite_client.get("/api/v1/settings/engines", headers=viewer)
    assert resp.status_code == 200
