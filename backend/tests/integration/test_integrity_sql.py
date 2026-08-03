"""real-SQL lite coverage: integrity verify + read-only report.

the integrity-report endpoint used to 500 on any real asset because
custody details carry bools/lists and the report schema demanded
dict[str, str]; the api tests masked it by patching the service.
this drives the unpatched service against a real sqlite db + local
storage: verify stamps recency columns (visible via GET asset), the
report reflects stored state, and generating a report writes no
custody entries.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
import pytest_asyncio

import loom.config
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


async def _custody_total(
    ac: httpx.AsyncClient,
    headers: dict[str, str],
    case_id: str,
    asset_id: str,
) -> int:
    resp = await ac.get(
        f"/api/v1/cases/{case_id}/assets/{asset_id}/custody",
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    return int(resp.json()["total"])


@pytest.mark.asyncio
async def test_verify_stamps_recency_visible_via_get_asset(
    lite_client: httpx.AsyncClient,
) -> None:
    headers = await _admin_headers(lite_client)
    case_id = await _make_case(lite_client, headers)
    asset_id = await _upload_asset(lite_client, headers, case_id)

    before = await lite_client.get(
        f"/api/v1/cases/{case_id}/assets/{asset_id}",
        headers=headers,
    )
    assert before.status_code == 200, before.text
    assert before.json()["last_verified_at"] is None
    assert before.json()["last_verification_ok"] is None

    verify = await lite_client.post(
        f"/api/v1/cases/{case_id}/assets/{asset_id}/verify",
        headers=headers,
    )
    assert verify.status_code == 200, verify.text
    assert verify.json()["passed"] is True

    after = await lite_client.get(
        f"/api/v1/cases/{case_id}/assets/{asset_id}",
        headers=headers,
    )
    assert after.json()["last_verification_ok"] is True
    assert after.json()["last_verified_at"] is not None


@pytest.mark.asyncio
async def test_report_serves_real_custody_details_read_only(
    lite_client: httpx.AsyncClient,
) -> None:
    """regression: the unpatched report must not 500 on real data.

    a real verification run writes bool-valued custody detail; the
    report must serialize it, reflect the stored recency columns,
    and leave the custody chain untouched.
    """
    headers = await _admin_headers(lite_client)
    case_id = await _make_case(lite_client, headers)
    asset_id = await _upload_asset(lite_client, headers, case_id)

    verify = await lite_client.post(
        f"/api/v1/cases/{case_id}/assets/{asset_id}/verify",
        headers=headers,
    )
    assert verify.status_code == 200, verify.text

    total_before = await _custody_total(lite_client, headers, case_id, asset_id)

    report = await lite_client.get(
        f"/api/v1/cases/{case_id}/assets/{asset_id}/integrity-report",
        headers=headers,
    )
    assert report.status_code == 200, report.text
    body = report.json()
    assert body["last_verification_ok"] is True
    assert body["sha256_hash"] == verify.json()["computed_sha256"]

    history = body["verification_history"]
    assert len(history) == 1
    assert history[0]["detail"]["sha256_match"] is True

    total_after = await _custody_total(lite_client, headers, case_id, asset_id)
    assert total_after == total_before


@pytest.mark.asyncio
async def test_report_404_for_unknown_asset(
    lite_client: httpx.AsyncClient,
) -> None:
    headers = await _admin_headers(lite_client)
    case_id = await _make_case(lite_client, headers)

    resp = await lite_client.get(
        f"/api/v1/cases/{case_id}/assets/"
        "00000000-0000-0000-0000-000000000099/integrity-report",
        headers=headers,
    )
    assert resp.status_code == 404, resp.text
