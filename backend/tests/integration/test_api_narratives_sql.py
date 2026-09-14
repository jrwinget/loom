"""real-SQL coverage for ai-drafted custody/audit narratives.

the single most legally-important assertion in this suite is
``test_only_approved_narratives_enter_the_export_manifest``: a draft or
a rejected narrative must never be reachable through the export
pipeline, only an explicitly human-approved one.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
import pytest_asyncio

import loom.config
from loom.security.auth import create_access_token
from loom.security.rate_limit import limiter
from loom.services import narrative_generation as narrative_module
from loom.services.export import build_export_manifest
from loom.services.text_generation import TextGenerationResult
from loom.workflows import shared
from loom.workflows.dispatch import drain_background_tasks

_MINIMAL_PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"

_ADMIN = {
    "admin_email": "ada@example.org",
    "admin_password": "correct-horse-battery",
    "admin_full_name": "Ada Admin",
}

_NARRATIVE_TEXT = "On the dates below, the following custody events occurred."


@pytest.fixture(autouse=True)
def _reset_rate_limiter() -> None:
    limiter.reset()


@pytest.fixture(autouse=True)
def _fake_generate_text(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake(*, provider, base_url, api_key, model, **kwargs):
        return TextGenerationResult(
            text=_NARRATIVE_TEXT,
            model=model,
            provenance={
                "provider": provider,
                "endpoint": "host",
                "model": model,
            },
        )

    monkeypatch.setattr(narrative_module, "generate_text", _fake)


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


async def _editor_headers(
    ac: httpx.AsyncClient,
    admin_headers: dict[str, str],
    case_id: str,
) -> dict[str, str]:
    resp = await ac.post(
        "/api/v1/auth/register-user",
        json={
            "email": "eve.editor@example.org",
            "display_name": "Eve Editor",
            "password": "Correct-Horse-Battery-9",
        },
        headers=admin_headers,
    )
    assert resp.status_code == 201, resp.text
    user_id = str(resp.json()["id"])

    resp = await ac.post(
        f"/api/v1/cases/{case_id}/members",
        json={"user_id": user_id, "role": "editor"},
        headers=admin_headers,
    )
    assert resp.status_code == 201, resp.text

    token = create_access_token(user_id, "analyst")
    return {"Authorization": f"Bearer {token}"}


async def _viewer_headers(
    ac: httpx.AsyncClient,
    admin_headers: dict[str, str],
    case_id: str,
) -> dict[str, str]:
    resp = await ac.post(
        "/api/v1/auth/register-user",
        json={
            "email": "victor.viewer@example.org",
            "display_name": "Victor Viewer",
            "password": "Correct-Horse-Battery-9",
        },
        headers=admin_headers,
    )
    assert resp.status_code == 201, resp.text
    user_id = str(resp.json()["id"])

    resp = await ac.post(
        f"/api/v1/cases/{case_id}/members",
        json={"user_id": user_id, "role": "viewer"},
        headers=admin_headers,
    )
    assert resp.status_code == 201, resp.text

    token = create_access_token(user_id, "analyst")
    return {"Authorization": f"Bearer {token}"}


async def _enable_text_generation(
    ac: httpx.AsyncClient, headers: dict[str, str]
) -> None:
    resp = await ac.put(
        "/api/v1/settings/ai/text-generation",
        json={
            "enabled": True,
            "provider": "oss",
            "api_base_url": "https://my-llm.example.com/v1",
            "model": "my-model",
        },
        headers=headers,
    )
    assert resp.status_code == 200, resp.text


@pytest.mark.asyncio
async def test_generate_list_and_approve_case_narrative(
    lite_client: httpx.AsyncClient,
) -> None:
    headers = await _admin_headers(lite_client)
    await _enable_text_generation(lite_client, headers)
    case_id = await _make_case(lite_client, headers)
    await _upload_asset(lite_client, headers, case_id)
    await drain_background_tasks()

    resp = await lite_client.post(
        f"/api/v1/cases/{case_id}/narratives", json={}, headers=headers
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "draft"
    assert body["text"] == _NARRATIVE_TEXT
    assert body["asset_id"] is None
    narrative_id = body["id"]

    listed = await lite_client.get(
        f"/api/v1/cases/{case_id}/narratives", headers=headers
    )
    assert listed.status_code == 200, listed.text
    assert len(listed.json()["items"]) == 1

    approved = await lite_client.post(
        f"/api/v1/cases/{case_id}/narratives/{narrative_id}/approve",
        headers=headers,
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "approved"
    assert approved.json()["reviewed_by"] is not None
    assert approved.json()["reviewed_at"] is not None


@pytest.mark.asyncio
async def test_asset_scoped_narrative(lite_client: httpx.AsyncClient) -> None:
    headers = await _admin_headers(lite_client)
    await _enable_text_generation(lite_client, headers)
    case_id = await _make_case(lite_client, headers)
    asset_id = await _upload_asset(lite_client, headers, case_id)
    await drain_background_tasks()

    resp = await lite_client.post(
        f"/api/v1/cases/{case_id}/narratives",
        json={"asset_id": asset_id},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["asset_id"] == asset_id


@pytest.mark.asyncio
async def test_viewer_cannot_generate_or_approve(
    lite_client: httpx.AsyncClient,
) -> None:
    headers = await _admin_headers(lite_client)
    await _enable_text_generation(lite_client, headers)
    case_id = await _make_case(lite_client, headers)
    viewer = await _viewer_headers(lite_client, headers, case_id)

    resp = await lite_client.post(
        f"/api/v1/cases/{case_id}/narratives", json={}, headers=viewer
    )
    assert resp.status_code == 403, resp.text

    # a viewer can still list/read (viewer+ access)
    resp = await lite_client.get(
        f"/api/v1/cases/{case_id}/narratives", headers=viewer
    )
    assert resp.status_code == 200, resp.text


@pytest.mark.asyncio
async def test_editor_can_generate_and_approve(
    lite_client: httpx.AsyncClient,
) -> None:
    headers = await _admin_headers(lite_client)
    await _enable_text_generation(lite_client, headers)
    case_id = await _make_case(lite_client, headers)
    editor = await _editor_headers(lite_client, headers, case_id)
    await _upload_asset(lite_client, headers, case_id)
    await drain_background_tasks()

    resp = await lite_client.post(
        f"/api/v1/cases/{case_id}/narratives", json={}, headers=editor
    )
    assert resp.status_code == 201, resp.text
    narrative_id = resp.json()["id"]

    resp = await lite_client.post(
        f"/api/v1/cases/{case_id}/narratives/{narrative_id}/approve",
        headers=editor,
    )
    assert resp.status_code == 200, resp.text


@pytest.mark.asyncio
async def test_generation_refused_under_litigation_hold(
    lite_client: httpx.AsyncClient,
) -> None:
    headers = await _admin_headers(lite_client)
    await _enable_text_generation(lite_client, headers)
    case_id = await _make_case(lite_client, headers)

    hold = await lite_client.post(
        f"/api/v1/cases/{case_id}/hold",
        json={"reason": "pending litigation"},
        headers=headers,
    )
    assert hold.status_code == 200, hold.text

    resp = await lite_client.post(
        f"/api/v1/cases/{case_id}/narratives", json={}, headers=headers
    )
    assert resp.status_code == 400, resp.text
    assert "litigation hold" in resp.text.lower()


@pytest.mark.asyncio
async def test_only_approved_narratives_enter_the_export_manifest(
    lite_client: httpx.AsyncClient,
) -> None:
    headers = await _admin_headers(lite_client)
    await _enable_text_generation(lite_client, headers)
    case_id = await _make_case(lite_client, headers)
    await _upload_asset(lite_client, headers, case_id)
    await drain_background_tasks()

    # a draft that is never reviewed
    draft_resp = await lite_client.post(
        f"/api/v1/cases/{case_id}/narratives", json={}, headers=headers
    )
    assert draft_resp.status_code == 201, draft_resp.text
    draft_id = draft_resp.json()["id"]

    # a narrative that is explicitly rejected
    rejected_resp = await lite_client.post(
        f"/api/v1/cases/{case_id}/narratives", json={}, headers=headers
    )
    assert rejected_resp.status_code == 201, rejected_resp.text
    rejected_id = rejected_resp.json()["id"]
    reject = await lite_client.post(
        f"/api/v1/cases/{case_id}/narratives/{rejected_id}/reject",
        headers=headers,
    )
    assert reject.status_code == 200, reject.text

    # a narrative that is explicitly approved
    approved_resp = await lite_client.post(
        f"/api/v1/cases/{case_id}/narratives", json={}, headers=headers
    )
    assert approved_resp.status_code == 201, approved_resp.text
    approved_id = approved_resp.json()["id"]
    approve = await lite_client.post(
        f"/api/v1/cases/{case_id}/narratives/{approved_id}/approve",
        headers=headers,
    )
    assert approve.status_code == 200, approve.text

    async with shared.get_db_session() as session:
        manifest = await build_export_manifest(
            session, case_id, {"include_analysis": True}
        )

    manifest_ids = {n["id"] for n in manifest["narratives"]}
    assert manifest_ids == {approved_id}
    assert draft_id not in manifest_ids
    assert rejected_id not in manifest_ids
    assert manifest["contents"]["included"]["narratives"] == 1
