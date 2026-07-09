"""real-SQL lite coverage: the case purge (destroy) endpoint.

destroying a case is irreversible, so the invariant under test is
strict: an append-only audit tombstone recording exactly what was
destroyed (title, reason, asset ids + hashes) must land *before* any
row or original is deleted, the case must be closed/archived first,
the exact title must be confirmed, and only an owner may do it. this
boots the sidecar the way tauri does (bootstrap_schema_if_lite,
lifespan, local filesystem storage) so cascade + storage deletion run
against a real sqlite db and the WORM bucket dir.
"""

from __future__ import annotations

import hashlib
from collections.abc import AsyncIterator
from pathlib import Path
from uuid import UUID

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import select

import loom.config
from loom.models.asset import Asset
from loom.models.audit import AuditLogEntry
from loom.models.case import Case
from loom.security.auth import create_access_token
from loom.security.rate_limit import limiter
from loom.workflows import shared
from loom.workflows.dispatch import drain_background_tasks

_MINIMAL_PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"

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
        json={"name": "Operation Nightingale", "description": "d"},
        headers=headers,
    )
    assert resp.status_code in (200, 201), resp.text
    return str(resp.json()["id"])


async def _upload_asset(
    ac: httpx.AsyncClient, headers: dict[str, str], case_id: str
) -> str:
    resp = await ac.post(
        f"/api/v1/cases/{case_id}/assets/upload-stream?filename=evidence.pdf",
        content=_MINIMAL_PDF,
        headers={**headers, "Content-Type": "application/octet-stream"},
    )
    assert resp.status_code == 201, resp.text
    return str(resp.json()["id"])


async def _close_case(
    ac: httpx.AsyncClient, headers: dict[str, str], case_id: str
) -> None:
    resp = await ac.patch(
        f"/api/v1/cases/{case_id}",
        json={"status": "closed"},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text


async def _asset_row(asset_id: str) -> Asset:
    async with shared.get_db_session() as session:
        result = await session.execute(
            select(Asset).where(Asset.id == UUID(asset_id))
        )
        return result.scalar_one()


@pytest.mark.asyncio
async def test_purge_rejected_while_active(
    lite_client: httpx.AsyncClient,
    lite_env: Path,
) -> None:
    headers = await _admin_headers(lite_client)
    case_id = await _make_case(lite_client, headers)
    asset_id = await _upload_asset(lite_client, headers, case_id)
    await drain_background_tasks()

    resp = await lite_client.request(
        "DELETE",
        f"/api/v1/cases/{case_id}",
        json={"confirm_title": "Operation Nightingale", "reason": "done"},
        headers=headers,
    )
    assert resp.status_code == 409, resp.text

    # nothing was destroyed
    asset = await _asset_row(asset_id)
    stored = lite_env / "buckets" / "loom-originals" / asset.storage_key
    assert stored.exists()


@pytest.mark.asyncio
async def test_purge_writes_tombstone_then_destroys(
    lite_client: httpx.AsyncClient,
    lite_env: Path,
) -> None:
    headers = await _admin_headers(lite_client)
    case_id = await _make_case(lite_client, headers)
    asset_id = await _upload_asset(lite_client, headers, case_id)
    await drain_background_tasks()

    asset = await _asset_row(asset_id)
    storage_key = asset.storage_key
    sha256 = asset.sha256_hash
    assert sha256 == hashlib.sha256(_MINIMAL_PDF).hexdigest()
    stored = lite_env / "buckets" / "loom-originals" / storage_key
    assert stored.exists()

    await _close_case(lite_client, headers, case_id)

    resp = await lite_client.request(
        "DELETE",
        f"/api/v1/cases/{case_id}",
        json={
            "confirm_title": "Operation Nightingale",
            "reason": "retention window elapsed",
        },
        headers=headers,
    )
    assert resp.status_code == 204, resp.text

    async with shared.get_db_session() as session:
        tomb = await session.execute(
            select(AuditLogEntry).where(AuditLogEntry.action == "case_purged")
        )
        entry = tomb.scalar_one()
        assert entry.resource_type == "cases"
        assert str(entry.resource_id) == case_id
        detail = entry.detail
        assert detail["title"] == "Operation Nightingale"
        assert detail["reason"] == "retention window elapsed"
        assert detail["asset_count"] == 1
        assert detail["assets"][0]["id"] == asset_id
        assert detail["assets"][0]["sha256"] == sha256
        assert detail["assets"][0]["original_filename"] == "evidence.pdf"

        case_left = await session.execute(
            select(Case).where(Case.id == UUID(case_id))
        )
        assert case_left.scalar_one_or_none() is None
        assets_left = await session.execute(
            select(Asset).where(Asset.case_id == UUID(case_id))
        )
        assert assets_left.scalars().first() is None

    assert not stored.exists()


@pytest.mark.asyncio
async def test_purge_wrong_title_destroys_nothing(
    lite_client: httpx.AsyncClient,
    lite_env: Path,
) -> None:
    headers = await _admin_headers(lite_client)
    case_id = await _make_case(lite_client, headers)
    asset_id = await _upload_asset(lite_client, headers, case_id)
    await drain_background_tasks()
    await _close_case(lite_client, headers, case_id)

    resp = await lite_client.request(
        "DELETE",
        f"/api/v1/cases/{case_id}",
        json={"confirm_title": "wrong name", "reason": "oops"},
        headers=headers,
    )
    assert resp.status_code == 400, resp.text

    asset = await _asset_row(asset_id)
    stored = lite_env / "buckets" / "loom-originals" / asset.storage_key
    assert stored.exists()
    async with shared.get_db_session() as session:
        case_left = await session.execute(
            select(Case).where(Case.id == UUID(case_id))
        )
        assert case_left.scalar_one_or_none() is not None


@pytest.mark.asyncio
async def test_purge_blank_reason_rejected(
    lite_client: httpx.AsyncClient,
) -> None:
    headers = await _admin_headers(lite_client)
    case_id = await _make_case(lite_client, headers)
    await _close_case(lite_client, headers, case_id)

    resp = await lite_client.request(
        "DELETE",
        f"/api/v1/cases/{case_id}",
        json={"confirm_title": "Operation Nightingale", "reason": "   "},
        headers=headers,
    )
    assert resp.status_code == 422, resp.text


@pytest.mark.asyncio
async def test_purge_non_owner_forbidden(
    lite_client: httpx.AsyncClient,
    lite_env: Path,
) -> None:
    headers = await _admin_headers(lite_client)
    case_id = await _make_case(lite_client, headers)
    asset_id = await _upload_asset(lite_client, headers, case_id)
    await drain_background_tasks()
    await _close_case(lite_client, headers, case_id)

    # a token for a user with no membership on this case
    outsider = create_access_token(
        "11111111-2222-7333-8444-555555555555", "analyst"
    )
    resp = await lite_client.request(
        "DELETE",
        f"/api/v1/cases/{case_id}",
        json={"confirm_title": "Operation Nightingale", "reason": "nope"},
        headers={"Authorization": f"Bearer {outsider}"},
    )
    assert resp.status_code == 403, resp.text

    asset = await _asset_row(asset_id)
    stored = lite_env / "buckets" / "loom-originals" / asset.storage_key
    assert stored.exists()
