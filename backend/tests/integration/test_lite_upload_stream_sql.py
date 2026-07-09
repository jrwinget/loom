"""real-SQL lite coverage: the streaming upload route end to end.

the multipart route buffers whole files in memory, which capped
desktop ingest at the configured limit and made multi-gb evidence
impossible. the raw-body route streams to a temp file and moves the
bytes into WORM storage; this exercises that path exactly the way
the tauri sidecar runs it (bootstrap_schema_if_lite, lifespan, local
filesystem storage).
"""

from __future__ import annotations

import hashlib
import stat
from collections.abc import AsyncIterator
from pathlib import Path
from uuid import UUID

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import select

import loom.config
from loom.models.asset import Asset
from loom.models.chain_of_custody import ChainOfCustodyEntry
from loom.security.rate_limit import limiter
from loom.workflows import shared
from loom.workflows.dispatch import drain_background_tasks

_MINIMAL_PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"
# a body large enough to arrive in multiple asgi chunks
_LARGE_PDF = _MINIMAL_PDF + b"0" * (2 * 1024 * 1024)

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
    """point the process at a fresh lite sqlite db and bootstrap it."""
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


async def _auth(ac: httpx.AsyncClient) -> dict[str, str]:
    resp = await ac.post("/api/v1/first-run/complete", json=_ADMIN)
    assert resp.status_code == 201, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


async def _case(ac: httpx.AsyncClient, headers: dict[str, str]) -> str:
    case = await ac.post(
        "/api/v1/cases",
        json={"name": "matter", "description": "d"},
        headers=headers,
    )
    assert case.status_code in (200, 201), case.text
    return str(case.json()["id"])


@pytest.mark.asyncio
async def test_streamed_upload_lands_in_worm_storage(
    lite_client: httpx.AsyncClient,
    lite_env: Path,
) -> None:
    headers = await _auth(lite_client)
    case_id = await _case(lite_client, headers)

    up = await lite_client.post(
        f"/api/v1/cases/{case_id}/assets/upload-stream?filename=evidence.pdf",
        content=_LARGE_PDF,
        headers={**headers, "Content-Type": "application/octet-stream"},
    )
    assert up.status_code == 201, up.text
    body = up.json()
    asset_id = body["id"]

    # streamed hash matches the whole-file digest
    assert body["sha256_hash"] == hashlib.sha256(_LARGE_PDF).hexdigest()

    await drain_background_tasks()

    async with shared.get_db_session() as session:
        result = await session.execute(
            select(Asset).where(Asset.id == UUID(asset_id))
        )
        asset = result.scalar_one()
        custody = await session.execute(
            select(ChainOfCustodyEntry).where(
                ChainOfCustodyEntry.asset_id == UUID(asset_id)
            )
        )
        actions = [c.action for c in custody.scalars()]

    assert asset.processing_status == "complete"
    assert asset.file_size_bytes == len(_LARGE_PDF)
    assert "upload" in actions

    # the original landed read-only (WORM) with the exact bytes
    stored = lite_env / "buckets" / "loom-originals" / asset.storage_key
    assert stored.exists()
    assert stored.read_bytes() == _LARGE_PDF
    assert not stored.stat().st_mode & stat.S_IWUSR

    # no temp file left behind
    tmp_dir = lite_env / "tmp-uploads"
    assert list(tmp_dir.iterdir()) == []


@pytest.mark.asyncio
async def test_streamed_upload_rejects_oversize_declared_length(
    lite_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers = await _auth(lite_client)
    case_id = await _case(lite_client, headers)

    settings = loom.config.get_settings()
    monkeypatch.setattr(settings, "max_upload_size_bytes", 1024)

    up = await lite_client.post(
        f"/api/v1/cases/{case_id}/assets/upload-stream?filename=big.pdf",
        content=_LARGE_PDF,
        headers={**headers, "Content-Type": "application/octet-stream"},
    )
    assert up.status_code == 413, up.text


@pytest.mark.asyncio
async def test_streamed_upload_rejects_lying_content_length(
    lite_client: httpx.AsyncClient,
    lite_env: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers = await _auth(lite_client)
    case_id = await _case(lite_client, headers)

    settings = loom.config.get_settings()
    monkeypatch.setattr(settings, "max_upload_size_bytes", 1024)

    # declare an in-cap length but stream more than the cap
    up = await lite_client.post(
        f"/api/v1/cases/{case_id}/assets/upload-stream?filename=liar.pdf",
        content=_LARGE_PDF,
        headers={
            **headers,
            "Content-Type": "application/octet-stream",
            "Content-Length": "512",
        },
    )
    assert up.status_code == 413, up.text

    # the partial temp file was cleaned up
    tmp_dir = lite_env / "tmp-uploads"
    if tmp_dir.exists():
        assert list(tmp_dir.iterdir()) == []


@pytest.mark.asyncio
async def test_streamed_upload_requires_content_length(
    lite_client: httpx.AsyncClient,
) -> None:
    headers = await _auth(lite_client)
    case_id = await _case(lite_client, headers)

    async def body() -> AsyncIterator[bytes]:
        yield _MINIMAL_PDF

    # chunked transfer omits content-length
    up = await lite_client.post(
        f"/api/v1/cases/{case_id}/assets/upload-stream?filename=x.pdf",
        content=body(),
        headers={**headers, "Content-Type": "application/octet-stream"},
    )
    assert up.status_code == 411, up.text


@pytest.mark.asyncio
async def test_streamed_upload_rejects_unsupported_type(
    lite_client: httpx.AsyncClient,
    lite_env: Path,
) -> None:
    headers = await _auth(lite_client)
    case_id = await _case(lite_client, headers)

    up = await lite_client.post(
        f"/api/v1/cases/{case_id}/assets/upload-stream?filename=evil.exe",
        content=b"MZ" + b"\x00" * 64,
        headers={**headers, "Content-Type": "application/octet-stream"},
    )
    assert up.status_code == 415, up.text

    # rejected bodies leave no temp file behind
    tmp_dir = lite_env / "tmp-uploads"
    if tmp_dir.exists():
        assert list(tmp_dir.iterdir()) == []
