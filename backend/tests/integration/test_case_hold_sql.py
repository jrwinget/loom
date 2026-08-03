"""real-SQL lite coverage: the litigation hold endpoints.

a litigation hold is a preservation lock (frcp 37(e) posture): while a
case is held, purge and asset deletion must be impossible. the
invariants under test are strict: only an owner may set or release a
hold, both actions land an audit entry in the same commit as the flag
change, a blank reason is rejected, and destructive endpoints refuse
with 409 while the hold is active. this boots the sidecar the way
tauri does (bootstrap_schema_if_lite, lifespan, local filesystem
storage) so the guards run against a real sqlite db.
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


async def _set_hold(
    ac: httpx.AsyncClient,
    headers: dict[str, str],
    case_id: str,
    reason: str = "pending litigation",
) -> httpx.Response:
    return await ac.post(
        f"/api/v1/cases/{case_id}/hold",
        json={"reason": reason},
        headers=headers,
    )


async def _release_hold(
    ac: httpx.AsyncClient,
    headers: dict[str, str],
    case_id: str,
    reason: str = "matter settled",
) -> httpx.Response:
    return await ac.post(
        f"/api/v1/cases/{case_id}/hold/release",
        json={"reason": reason},
        headers=headers,
    )


async def _editor_headers(
    ac: httpx.AsyncClient,
    admin_headers: dict[str, str],
    case_id: str,
) -> dict[str, str]:
    """create a non-admin user, grant editor on the case, mint a token."""
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


@pytest.mark.asyncio
async def test_set_hold_persists_fields_and_audits(
    lite_client: httpx.AsyncClient,
) -> None:
    headers = await _admin_headers(lite_client)
    case_id = await _make_case(lite_client, headers)

    resp = await _set_hold(
        lite_client, headers, case_id, reason="doe v. city litigation"
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["hold_active"] is True
    assert body["hold_reason"] == "doe v. city litigation"
    assert body["hold_set_by"] is not None
    assert body["hold_set_at"] is not None

    async with shared.get_db_session() as session:
        row = await session.execute(
            select(Case).where(Case.id == UUID(case_id))
        )
        case = row.scalar_one()
        assert case.hold_active is True
        assert case.hold_reason == "doe v. city litigation"
        assert case.hold_set_by is not None
        assert case.hold_set_at is not None

        audit = await session.execute(
            select(AuditLogEntry).where(AuditLogEntry.action == "case_hold_set")
        )
        entry = audit.scalar_one()
        assert entry.resource_type == "cases"
        assert str(entry.resource_id) == case_id
        assert entry.detail["reason"] == "doe v. city litigation"


@pytest.mark.asyncio
async def test_set_hold_blank_reason_rejected(
    lite_client: httpx.AsyncClient,
) -> None:
    headers = await _admin_headers(lite_client)
    case_id = await _make_case(lite_client, headers)

    resp = await _set_hold(lite_client, headers, case_id, reason="   ")
    assert resp.status_code == 422, resp.text

    resp = await _set_hold(lite_client, headers, case_id, reason="")
    assert resp.status_code == 422, resp.text


@pytest.mark.asyncio
async def test_hold_requires_owner(
    lite_client: httpx.AsyncClient,
) -> None:
    headers = await _admin_headers(lite_client)
    case_id = await _make_case(lite_client, headers)
    editor = await _editor_headers(lite_client, headers, case_id)

    resp = await _set_hold(lite_client, editor, case_id)
    assert resp.status_code == 403, resp.text

    resp = await _release_hold(lite_client, editor, case_id)
    assert resp.status_code == 403, resp.text

    # a token for a user with no membership on this case
    outsider = create_access_token(
        "11111111-2222-7333-8444-555555555555", "analyst"
    )
    outsider_headers = {"Authorization": f"Bearer {outsider}"}
    resp = await _set_hold(lite_client, outsider_headers, case_id)
    assert resp.status_code == 403, resp.text


@pytest.mark.asyncio
async def test_double_set_and_release_when_not_held_conflict(
    lite_client: httpx.AsyncClient,
) -> None:
    headers = await _admin_headers(lite_client)
    case_id = await _make_case(lite_client, headers)

    resp = await _release_hold(lite_client, headers, case_id)
    assert resp.status_code == 409, resp.text

    resp = await _set_hold(lite_client, headers, case_id)
    assert resp.status_code == 200, resp.text

    resp = await _set_hold(lite_client, headers, case_id)
    assert resp.status_code == 409, resp.text


@pytest.mark.asyncio
async def test_release_clears_fields_and_audits(
    lite_client: httpx.AsyncClient,
) -> None:
    headers = await _admin_headers(lite_client)
    case_id = await _make_case(lite_client, headers)

    resp = await _set_hold(lite_client, headers, case_id)
    assert resp.status_code == 200, resp.text

    resp = await _release_hold(
        lite_client, headers, case_id, reason="settled 2026-07-20"
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["hold_active"] is False
    assert body["hold_reason"] is None
    assert body["hold_set_by"] is None
    assert body["hold_set_at"] is None

    async with shared.get_db_session() as session:
        audit = await session.execute(
            select(AuditLogEntry).where(
                AuditLogEntry.action == "case_hold_released"
            )
        )
        entry = audit.scalar_one()
        assert entry.resource_type == "cases"
        assert str(entry.resource_id) == case_id
        assert entry.detail["reason"] == "settled 2026-07-20"


@pytest.mark.asyncio
async def test_purge_refused_while_held(
    lite_client: httpx.AsyncClient,
) -> None:
    headers = await _admin_headers(lite_client)
    case_id = await _make_case(lite_client, headers)
    await _close_case(lite_client, headers, case_id)

    resp = await _set_hold(lite_client, headers, case_id)
    assert resp.status_code == 200, resp.text

    resp = await lite_client.request(
        "DELETE",
        f"/api/v1/cases/{case_id}",
        json={"confirm_title": "Operation Nightingale", "reason": "done"},
        headers=headers,
    )
    assert resp.status_code == 409, resp.text
    assert resp.json()["detail"] == "case is under litigation hold"

    async with shared.get_db_session() as session:
        row = await session.execute(
            select(Case).where(Case.id == UUID(case_id))
        )
        assert row.scalar_one_or_none() is not None

    resp = await _release_hold(lite_client, headers, case_id)
    assert resp.status_code == 200, resp.text

    resp = await lite_client.request(
        "DELETE",
        f"/api/v1/cases/{case_id}",
        json={"confirm_title": "Operation Nightingale", "reason": "done"},
        headers=headers,
    )
    assert resp.status_code == 204, resp.text


@pytest.mark.asyncio
async def test_hold_guard_wins_over_status_guard(
    lite_client: httpx.AsyncClient,
) -> None:
    # an active (not closed/archived) case under hold must report the
    # hold, not the lifecycle-status conflict
    headers = await _admin_headers(lite_client)
    case_id = await _make_case(lite_client, headers)

    resp = await _set_hold(lite_client, headers, case_id)
    assert resp.status_code == 200, resp.text

    resp = await lite_client.request(
        "DELETE",
        f"/api/v1/cases/{case_id}",
        json={"confirm_title": "Operation Nightingale", "reason": "done"},
        headers=headers,
    )
    assert resp.status_code == 409, resp.text
    assert resp.json()["detail"] == "case is under litigation hold"


@pytest.mark.asyncio
async def test_asset_delete_refused_while_held(
    lite_client: httpx.AsyncClient,
) -> None:
    headers = await _admin_headers(lite_client)
    case_id = await _make_case(lite_client, headers)
    asset_id = await _upload_asset(lite_client, headers, case_id)
    await drain_background_tasks()

    resp = await _set_hold(lite_client, headers, case_id)
    assert resp.status_code == 200, resp.text

    resp = await lite_client.delete(
        f"/api/v1/cases/{case_id}/assets/{asset_id}",
        headers=headers,
    )
    assert resp.status_code == 409, resp.text
    assert resp.json()["detail"] == "case is under litigation hold"

    resp = await _release_hold(lite_client, headers, case_id)
    assert resp.status_code == 200, resp.text

    resp = await lite_client.delete(
        f"/api/v1/cases/{case_id}/assets/{asset_id}",
        headers=headers,
    )
    assert resp.status_code == 200, resp.text


@pytest.mark.asyncio
async def test_get_case_returns_hold_fields_and_real_asset_count(
    lite_client: httpx.AsyncClient,
) -> None:
    headers = await _admin_headers(lite_client)
    case_id = await _make_case(lite_client, headers)
    await _upload_asset(lite_client, headers, case_id)
    await drain_background_tasks()

    resp = await _set_hold(
        lite_client, headers, case_id, reason="anticipated litigation"
    )
    assert resp.status_code == 200, resp.text

    resp = await lite_client.get(f"/api/v1/cases/{case_id}", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["hold_active"] is True
    assert body["hold_reason"] == "anticipated litigation"
    # regression: the detail endpoint used to hardcode asset_count=0
    assert body["asset_count"] == 1
