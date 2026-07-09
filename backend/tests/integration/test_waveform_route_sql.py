"""real-SQL lite coverage: the audio waveform-peaks endpoint.

the route serves the real peak envelope produced at ingest. when no
peaks derivative exists (asset still processing, or ffmpeg was absent)
it must 404 cleanly so the player shows an honest "unavailable" state
rather than a fabricated shape. this boots the sidecar the way tauri
does (bootstrap_schema_if_lite, lifespan, local filesystem storage) and
drives the route against a real sqlite db + WORM bucket, inserting the
derivative row and its storage object directly (no ffmpeg needed).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import AsyncIterator
from pathlib import Path
from uuid import UUID

import httpx
import pytest
import pytest_asyncio

import loom.config
from loom.models.derivative import Derivative
from loom.security.rate_limit import limiter
from loom.services.storage_backends import DERIVATIVES_BUCKET
from loom.workflows import shared
from loom.workflows.dispatch import drain_background_tasks

_MINIMAL_PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"
_PEAKS = [0.0, 0.5, 1.0, 0.25]

_ADMIN = {
    "admin_email": "ada@example.org",
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
    yield tmp_path
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


async def _make_case(ac: httpx.AsyncClient, headers: dict[str, str]) -> str:
    resp = await ac.post(
        "/api/v1/cases",
        json={"name": "matter", "description": "d"},
        headers=headers,
    )
    assert resp.status_code in (200, 201), resp.text
    return str(resp.json()["id"])


async def _upload_asset(
    ac: httpx.AsyncClient, headers: dict[str, str], case_id: str
) -> str:
    resp = await ac.post(
        f"/api/v1/cases/{case_id}/assets/upload",
        files={"file": ("evidence.pdf", _MINIMAL_PDF, "application/pdf")},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    await drain_background_tasks()
    return str(resp.json()["id"])


async def _attach_peaks(case_id: str, asset_id: str) -> None:
    """write a peaks json object + derivative row directly."""
    key = f"{case_id}/{asset_id}/waveform_peaks.json"
    body = json.dumps({"peaks": _PEAKS, "version": 1}).encode()
    shared.get_storage_backend().upload_bytes(
        DERIVATIVES_BUCKET, key, body, "application/json"
    )
    async with shared.get_db_session() as session:
        session.add(
            Derivative(
                asset_id=UUID(asset_id),
                type="waveform_peaks",
                storage_key=key,
                mime_type="application/json",
                file_size_bytes=len(body),
                sha256_hash=hashlib.sha256(body).hexdigest(),
                generation_params={"sample_count": len(_PEAKS)},
            )
        )
        await session.commit()


@pytest.mark.asyncio
async def test_waveform_404_when_no_peaks_derivative(
    lite_client: httpx.AsyncClient,
) -> None:
    headers = await _admin_headers(lite_client)
    case_id = await _make_case(lite_client, headers)
    asset_id = await _upload_asset(lite_client, headers, case_id)

    resp = await lite_client.get(
        f"/api/v1/cases/{case_id}/assets/{asset_id}/waveform",
        headers=headers,
    )
    assert resp.status_code == 404, resp.text


@pytest.mark.asyncio
async def test_waveform_200_returns_stored_peaks(
    lite_client: httpx.AsyncClient,
) -> None:
    headers = await _admin_headers(lite_client)
    case_id = await _make_case(lite_client, headers)
    asset_id = await _upload_asset(lite_client, headers, case_id)
    await _attach_peaks(case_id, asset_id)

    resp = await lite_client.get(
        f"/api/v1/cases/{case_id}/assets/{asset_id}/waveform",
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["peaks"] == _PEAKS
