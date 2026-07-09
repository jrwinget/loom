"""global search must never leak across the membership boundary.

the load-bearing test: user B, searching the same term, sees their
own case and NOT user A's — even though both cases match. everything
else about the palette is cosmetic next to this.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import loom.config
from loom.models.case import Case, CaseMembership
from loom.models.user import User
from loom.security.auth import create_access_token, hash_password
from loom.security.rate_limit import limiter


@pytest.fixture(autouse=True)
def _reset_rate_limiter() -> None:
    limiter.reset()


@pytest.fixture
def lite_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
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
async def lite_client(lite_env: Path) -> AsyncIterator[httpx.AsyncClient]:
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


async def _seed(lite_env: Path) -> dict[str, str]:
    """two editors, one admin, a matching case owned by each editor.

    seeded directly since lite has no user-creation endpoint; the
    search boundary is profile-agnostic, so this exercises it fully.
    """
    engine = create_async_engine(f"sqlite+aiosqlite:///{lite_env}/loom.db")
    ids: dict[str, str] = {}
    try:
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as s:
            users = {}
            for name, role in (
                ("alice", "editor"),
                ("bob", "editor"),
                ("admin", "admin"),
            ):
                u = User(
                    email=f"{name}@example.org",
                    display_name=name,
                    role=role,
                    password_hash=hash_password("correct-horse-battery"),
                )
                s.add(u)
                await s.flush()
                users[name] = u
                ids[f"{name}_id"] = str(u.id)

            for owner in ("alice", "bob"):
                case = Case(
                    name=f"Surveillance {owner.title()}",
                    description="footage review",
                    created_by=users[owner].id,
                    status="active",
                )
                s.add(case)
                await s.flush()
                s.add(
                    CaseMembership(
                        case_id=case.id,
                        user_id=users[owner].id,
                        role="owner",
                        granted_by=users[owner].id,
                    )
                )
                ids[f"case_{owner}"] = str(case.id)
            await s.commit()
    finally:
        await engine.dispose()
    return ids


def _auth(user_id: str, role: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user_id, role)}"}


@pytest.mark.asyncio
async def test_search_is_scoped_to_membership(
    lite_client: httpx.AsyncClient, lite_env: Path
) -> None:
    ids = await _seed(lite_env)

    # alice sees only her case, though both match "Surveillance"
    resp = await lite_client.get(
        "/api/v1/search?q=Surveillance",
        headers=_auth(ids["alice_id"], "editor"),
    )
    assert resp.status_code == 200, resp.text
    found = {r["id"] for r in resp.json()["results"]}
    assert ids["case_alice"] in found
    assert ids["case_bob"] not in found, "alice must not see bob's case"

    # bob sees only his
    resp = await lite_client.get(
        "/api/v1/search?q=Surveillance",
        headers=_auth(ids["bob_id"], "editor"),
    )
    found = {r["id"] for r in resp.json()["results"]}
    assert ids["case_bob"] in found
    assert ids["case_alice"] not in found, "bob must not see alice's case"

    # admin sees both
    resp = await lite_client.get(
        "/api/v1/search?q=Surveillance",
        headers=_auth(ids["admin_id"], "admin"),
    )
    found = {r["id"] for r in resp.json()["results"]}
    assert {ids["case_alice"], ids["case_bob"]} <= found


@pytest.mark.asyncio
async def test_non_member_with_no_cases_sees_nothing(
    lite_client: httpx.AsyncClient, lite_env: Path
) -> None:
    await _seed(lite_env)
    # a valid token for a user who belongs to no case
    orphan = str(uuid4())
    resp = await lite_client.get(
        "/api/v1/search?q=Surveillance", headers=_auth(orphan, "editor")
    )
    assert resp.status_code == 200
    assert resp.json()["results"] == []


@pytest.mark.asyncio
async def test_empty_query_rejected(
    lite_client: httpx.AsyncClient, lite_env: Path
) -> None:
    ids = await _seed(lite_env)
    resp = await lite_client.get(
        "/api/v1/search?q=", headers=_auth(ids["admin_id"], "admin")
    )
    assert resp.status_code == 422
