"""real-SQL coverage for recovery-code regeneration and mfa disable.

the unit tests mock the session, so they never prove that regenerated
codes actually invalidate the old ones at the challenge endpoint, nor
that disabling clears enrollment in the row. this boots a real on-disk
sqlite db the way the sidecar does, seeds an enrolled admin, and drives
the endpoints end to end:

- regenerating with a live totp replaces the stored codes: the old
  recovery code stops completing the challenge and a fresh one works;
- disabling requires the account password (a stolen session token alone
  must not strip the second factor) and clears enrollment.
"""

from __future__ import annotations

import hashlib
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pyotp
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import loom.config
from loom.models.user import User
from loom.security.auth import (
    create_access_token,
    create_mfa_challenge_token,
    hash_password,
)
from loom.security.rate_limit import limiter

_PASSWORD = "correct-horse-battery"
_SECRET = pyotp.random_base32()


@pytest.fixture(autouse=True)
def _reset_rate_limiter() -> None:
    """challenge and regen are capped per minute; clear the process-wide
    limiter so the multi-call cases hit the handler, not a 429."""
    limiter.reset()


@pytest.fixture
def lite_env(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Path:
    """point the process at a fresh lite sqlite db and bootstrap it."""
    db_path = tmp_path / "loom.db"
    monkeypatch.setenv("LOOM_DEPLOYMENT_PROFILE", "lite")
    monkeypatch.setenv("LOOM_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("LOOM_DATABASE_URL", f"sqlite+aiosqlite:///{db_path}")
    monkeypatch.setenv("LOOM_SECRET_KEY", "x" * 48)
    monkeypatch.setenv("LOOM_STORAGE_SIGNING_SECRET", "y" * 48)

    loom.config.get_settings.cache_clear()
    from loom.__main__ import bootstrap_schema_if_lite

    bootstrap_schema_if_lite()
    yield db_path
    loom.config.get_settings.cache_clear()


@pytest_asyncio.fixture
async def lite_client(
    lite_env: Path,
) -> AsyncIterator[httpx.AsyncClient]:
    """yield a client served through the app lifespan so that
    app.state.db_session_factory points at the bootstrapped db."""
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


def _hash(code: str) -> str:
    return hashlib.sha256(code.encode()).hexdigest()


async def _seed_enrolled_admin(
    db_path: Path,
    recovery_plain: list[str],
) -> str:
    """insert an mfa-enrolled admin directly and return its id."""
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    # keep attributes live after commit so reading the generated id
    # doesn't trigger a lazy refresh outside the async greenlet.
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        user = User(
            email="mfa.user@example.com",
            display_name="MFA User",
            role="admin",
            password_hash=hash_password(_PASSWORD),
            mfa_enabled=True,
            mfa_secret=_SECRET,
            recovery_codes=",".join(_hash(c) for c in recovery_plain),
        )
        session.add(user)
        await session.commit()
        user_id = str(user.id)
    await engine.dispose()
    return user_id


@pytest.mark.asyncio
async def test_regenerate_invalidates_old_and_issues_working_codes(
    lite_env: Path,
    lite_client: httpx.AsyncClient,
) -> None:
    user_id = await _seed_enrolled_admin(lite_env, ["oldcode0001"])
    token = create_access_token(user_id, "admin")

    resp = await lite_client.post(
        "/api/v1/auth/mfa/recovery-codes",
        json={"code": pyotp.TOTP(_SECRET).now()},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text
    new_codes = resp.json()["recovery_codes"]
    assert len(new_codes) == 10

    # the previously-issued code no longer completes a challenge.
    old_challenge = create_mfa_challenge_token(user_id)
    stale = await lite_client.post(
        "/api/v1/auth/mfa/challenge",
        json={"challenge_token": old_challenge, "code": "oldcode0001"},
    )
    assert stale.status_code == 401, stale.text

    # a freshly-minted code does.
    new_challenge = create_mfa_challenge_token(user_id)
    fresh = await lite_client.post(
        "/api/v1/auth/mfa/challenge",
        json={"challenge_token": new_challenge, "code": new_codes[0]},
    )
    assert fresh.status_code == 200, fresh.text
    assert fresh.json()["access_token"]


@pytest.mark.asyncio
async def test_disable_requires_account_password(
    lite_env: Path,
    lite_client: httpx.AsyncClient,
) -> None:
    user_id = await _seed_enrolled_admin(lite_env, ["somecode0001"])
    token = create_access_token(user_id, "admin")
    headers = {"Authorization": f"Bearer {token}"}

    # a session token without the password cannot strip the factor.
    bad = await lite_client.request(
        "DELETE",
        "/api/v1/auth/mfa",
        json={"password": "not-my-password"},
        headers=headers,
    )
    assert bad.status_code == 401, bad.text
    still_on = await lite_client.get("/api/v1/auth/me", headers=headers)
    assert still_on.json()["mfa_enabled"] is True

    ok = await lite_client.request(
        "DELETE",
        "/api/v1/auth/mfa",
        json={"password": _PASSWORD},
        headers=headers,
    )
    assert ok.status_code == 204, ok.text
    now_off = await lite_client.get("/api/v1/auth/me", headers=headers)
    assert now_off.json()["mfa_enabled"] is False
