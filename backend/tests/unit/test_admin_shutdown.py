"""tests for the local-only POST /admin/shutdown endpoint.

the endpoint exists so the tauri desktop shell can ask the sidecar
to release port 8000 cleanly before falling back to a hard kill. we
verify the three states that matter:

  - token env unset (server-profile / dev invocation) -> 404 so the
    surface is invisible to external probes,
  - token env set, wrong token presented -> 401,
  - token env set, correct token presented -> 204 and os._exit is
    scheduled.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import httpx
import pytest
import pytest_asyncio

from loom.config import Settings, get_settings
from loom.security.rate_limit import limiter


@pytest.fixture(autouse=True)
def _reset_rate_limiter() -> None:
    limiter.reset()


@pytest_asyncio.fixture
def _settings_with_token() -> Settings:
    return Settings(
        secret_key="test-secret-key-that-is-long-enough-for-validation",
        database_url="sqlite+aiosqlite:///",
        shutdown_token="known-good-token",
    )


@pytest_asyncio.fixture
def _settings_without_token() -> Settings:
    return Settings(
        secret_key="test-secret-key-that-is-long-enough-for-validation",
        database_url="sqlite+aiosqlite:///",
        shutdown_token=None,
    )


def _build_app(cfg: Settings) -> Any:
    get_settings.cache_clear()
    with patch("loom.config.get_settings", return_value=cfg):
        from loom.main import create_app

        return create_app()


async def test_returns_404_when_shutdown_token_unset(
    _settings_without_token: Settings,
) -> None:
    """no env -> endpoint behaves as if it doesn't exist."""
    app = _build_app(_settings_without_token)
    with patch(
        "loom.api.v1.admin.get_settings",
        return_value=_settings_without_token,
    ):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            resp = await client.post(
                "/api/v1/admin/shutdown",
                headers={"X-Loom-Shutdown-Token": "anything"},
            )
    assert resp.status_code == 404


async def test_returns_401_on_wrong_token(
    _settings_with_token: Settings,
) -> None:
    app = _build_app(_settings_with_token)
    with patch(
        "loom.api.v1.admin.get_settings",
        return_value=_settings_with_token,
    ):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            resp = await client.post(
                "/api/v1/admin/shutdown",
                headers={"X-Loom-Shutdown-Token": "wrong"},
            )
    assert resp.status_code == 401


async def test_returns_401_when_header_missing(
    _settings_with_token: Settings,
) -> None:
    """missing header is presented as an empty string and rejected."""
    app = _build_app(_settings_with_token)
    with patch(
        "loom.api.v1.admin.get_settings",
        return_value=_settings_with_token,
    ):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            resp = await client.post("/api/v1/admin/shutdown")
    assert resp.status_code == 401


async def test_returns_204_and_schedules_exit_on_correct_token(
    _settings_with_token: Settings,
) -> None:
    """correct token -> 204 and a delayed os._exit(0)."""
    app = _build_app(_settings_with_token)

    scheduled: list[float] = []

    def _capture(delay: float) -> None:
        scheduled.append(delay)

    with (
        patch(
            "loom.api.v1.admin.get_settings",
            return_value=_settings_with_token,
        ),
        patch("loom.api.v1.admin._schedule_exit", side_effect=_capture),
    ):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            resp = await client.post(
                "/api/v1/admin/shutdown",
                headers={"X-Loom-Shutdown-Token": "known-good-token"},
            )

    assert resp.status_code == 204
    assert len(scheduled) == 1
    assert 0 < scheduled[0] <= 1.0
