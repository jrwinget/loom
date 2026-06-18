"""real-SQL lite coverage: an uploaded asset is processed in-process.

reproduces the desktop bug where an uploaded pdf sat at
processing_status 'pending' forever — nothing dispatched the ingest
pipeline, and the lite profile had no temporal worker to run it.
with the in-process facade, upload -> dispatch -> in-process ingest
advances the asset to 'complete' with no temporal server, and the
workflow-status endpoint reports it from the in-process state.

booted exactly the way the tauri sidecar boots: schema materialised
by ``bootstrap_schema_if_lite``, app served through its lifespan,
storage on the local filesystem.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from uuid import UUID

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import select

import loom.config
from loom.models.asset import Asset
from loom.security.rate_limit import limiter
from loom.workflows import shared
from loom.workflows.dispatch import drain_background_tasks

# minimal pdf: the %PDF- header is all puremagic needs to classify
# this as application/pdf -> media_type "document".
_MINIMAL_PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"

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
    # activities use the worker-side cached engine/backend; reset it so
    # it binds to this test's db and local storage, not a prior test's.
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


async def _auth(ac: httpx.AsyncClient) -> dict[str, str]:
    resp = await ac.post("/api/v1/first-run/complete", json=_ADMIN)
    assert resp.status_code == 201, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


@pytest.mark.asyncio
async def test_uploaded_pdf_is_processed_in_process(
    lite_client: httpx.AsyncClient,
) -> None:
    headers = await _auth(lite_client)

    case = await lite_client.post(
        "/api/v1/cases",
        json={"name": "matter", "description": "d"},
        headers=headers,
    )
    assert case.status_code in (200, 201), case.text
    case_id = case.json()["id"]

    up = await lite_client.post(
        f"/api/v1/cases/{case_id}/assets/upload",
        files={"file": ("evidence.pdf", _MINIMAL_PDF, "application/pdf")},
        headers=headers,
    )
    assert up.status_code == 201, up.text
    asset_id = up.json()["id"]
    # upload returns immediately; processing has not finished yet
    assert up.json()["processing_status"] == "pending"

    # the in-process ingest pipeline runs in the background
    await drain_background_tasks()

    # the asset advanced to complete with no temporal server involved
    async with shared.get_db_session() as session:
        result = await session.execute(
            select(Asset).where(Asset.id == UUID(asset_id))
        )
        asset = result.scalar_one()
    assert asset.processing_status == "complete"

    # and the workflow-status endpoint reports completion on lite
    status_resp = await lite_client.get(
        f"/api/v1/cases/{case_id}/workflows/ingest-{asset_id}/status",
        headers=headers,
    )
    assert status_resp.status_code == 200, status_resp.text
    assert status_resp.json()["status"] == "completed"
