"""real-SQL coverage for the AI settings endpoint (lite profile)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio

import loom.config
from loom.security.auth import create_access_token
from loom.security.rate_limit import limiter
from loom.workflows import shared

_ADMIN = {
    "admin_email": "admin@example.com",
    "admin_password": "correct-horse-battery",
    "admin_full_name": "Ada Admin",
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
async def test_get_defaults_then_set_cloud(
    lite_client: httpx.AsyncClient,
) -> None:
    headers = await _admin_headers(lite_client)

    got = await lite_client.get("/api/v1/settings/ai", headers=headers)
    assert got.status_code == 200, got.text
    assert got.json()["transcription_engine"] == "local"
    assert got.json()["provider"] == ""
    assert got.json()["api_key_set"] is False
    assert got.json()["provider_available"] is True
    assert got.json()["key_decryptable"] is True

    put = await lite_client.put(
        "/api/v1/settings/ai",
        json={
            "transcription_engine": "cloud",
            "provider": "custom",
            "api_key": "sk-secret",
            "api_base_url": "https://transcribe.example.com/v1",
            "transcription_model": "whisper-1",
        },
        headers=headers,
    )
    assert put.status_code == 200, put.text
    body = put.json()
    assert body["transcription_engine"] == "cloud"
    assert body["provider"] == "custom"
    assert body["api_base_url"] == "https://transcribe.example.com/v1"
    assert body["api_key_set"] is True
    # the key itself is never returned
    assert "api_key" not in body

    # persisted across requests, still masked, and still decryptable
    again = await lite_client.get("/api/v1/settings/ai", headers=headers)
    assert again.json()["transcription_engine"] == "cloud"
    assert again.json()["provider"] == "custom"
    assert again.json()["api_key_set"] is True
    assert again.json()["key_decryptable"] is True


@pytest.mark.asyncio
async def test_put_with_retired_provider_is_rejected(
    lite_client: httpx.AsyncClient,
) -> None:
    headers = await _admin_headers(lite_client)
    resp = await lite_client.put(
        "/api/v1/settings/ai",
        json={
            "transcription_engine": "cloud",
            "provider": "openai",
            "api_key": "sk-secret",
            "transcription_model": "gpt-4o-transcribe",
        },
        headers=headers,
    )
    assert resp.status_code == 400
    assert "unknown ai provider" in resp.text.lower()


@pytest.mark.asyncio
async def test_self_hosted_endpoint_may_be_local(
    lite_client: httpx.AsyncClient,
) -> None:
    # the open-source/self-hosted provider is allowed to target a local
    # server; only a malformed (non-http) url is rejected.
    headers = await _admin_headers(lite_client)
    ok = await lite_client.put(
        "/api/v1/settings/ai",
        json={
            "transcription_engine": "cloud",
            "provider": "oss",
            "transcription_model": "whisper-large-v3",
            "api_base_url": "http://localhost:9000/v1",
        },
        headers=headers,
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["api_base_url"] == "http://localhost:9000/v1"

    bad = await lite_client.put(
        "/api/v1/settings/ai",
        json={
            "transcription_engine": "cloud",
            "provider": "custom",
            "transcription_model": "whisper-1",
            "api_base_url": "not-a-url",
        },
        headers=headers,
    )
    assert bad.status_code == 400


@pytest.mark.asyncio
async def test_lists_providers(lite_client: httpx.AsyncClient) -> None:
    headers = await _admin_headers(lite_client)
    resp = await lite_client.get(
        "/api/v1/settings/ai/providers", headers=headers
    )
    assert resp.status_code == 200, resp.text
    by_id = {p["id"]: p for p in resp.json()["providers"]}
    assert set(by_id) == {"oss", "custom"}
    assert {"openai", "google", "anthropic"}.isdisjoint(by_id)
    # backend returns snake_case (the frontend api-client camelCases it)
    assert by_id["oss"]["requires_api_key"] is False
    assert any(m["id"] == "whisper-large-v3" for m in by_id["oss"]["models"])


@pytest.mark.asyncio
async def test_stale_frontier_config_reports_unavailable(
    lite_env: Path,
    lite_client: httpx.AsyncClient,
) -> None:
    # simulate an install that still has a pre-removal config saved
    # directly (bypassing the settings api, as a restored backup would).
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from loom.models.app_setting import AppSetting

    headers = await _admin_headers(lite_client)

    engine = create_async_engine(f"sqlite+aiosqlite:///{lite_env}")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        session.add(
            AppSetting(
                key="ai",
                value={
                    "transcription_engine": "cloud",
                    "provider": "openai",
                    "api_base_url": "https://api.openai.com/v1",
                    "api_key": "sk-stale",
                    "transcription_model": "gpt-4o-transcribe",
                    "whisper_model": "base",
                },
            )
        )
        await session.commit()
    await engine.dispose()

    resp = await lite_client.get("/api/v1/settings/ai", headers=headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["provider_available"] is False


@pytest.mark.asyncio
async def test_non_admin_cannot_update(
    lite_client: httpx.AsyncClient,
) -> None:
    await _admin_headers(lite_client)  # bootstrap so the app is set up
    viewer = create_access_token(str(uuid4()), "viewer")
    resp = await lite_client.put(
        "/api/v1/settings/ai",
        json={"transcription_engine": "local"},
        headers={"Authorization": f"Bearer {viewer}"},
    )
    assert resp.status_code == 403
