"""real-SQL coverage for the audit middleware.

the middleware only extracts a resource id when the request path has
a UUID segment, so collection-level routes (login, mfa, case create,
first-run) insert ``resource_id=None``. the mocked unit tests assert
``session.add`` was called and never compile the INSERT, which hid a
NOT NULL constraint violation that silently dropped every one of
those entries — the catch-all in the middleware downgrades the
failure to a warning. this boots a real sqlite db the way the
sidecar does and proves the entry actually commits.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import loom.config
from loom.models.audit import AuditLogEntry
from loom.security.rate_limit import limiter


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
    from loom.__main__ import bootstrap_schema_if_lite

    bootstrap_schema_if_lite()
    yield db_path
    loom.config.get_settings.cache_clear()


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


@pytest.mark.asyncio
async def test_collection_route_writes_audit_entry(
    lite_env: Path,
    lite_client: httpx.AsyncClient,
) -> None:
    """a mutating route without a UUID in the path must still land in
    the audit trail with a null resource id."""
    resp = await lite_client.post(
        "/api/v1/first-run/complete",
        json={
            "admin_email": "ada@example.org",
            "admin_password": "correct-horse-battery",
            "admin_full_name": "Ada Admin",
        },
    )
    assert resp.status_code == 201, resp.text

    engine = create_async_engine(f"sqlite+aiosqlite:///{lite_env}")
    try:
        factory = async_sessionmaker(engine)
        async with factory() as session:
            rows = (
                (
                    await session.execute(
                        select(AuditLogEntry).where(
                            AuditLogEntry.action
                            == "POST /api/v1/first-run/complete"
                        )
                    )
                )
                .scalars()
                .all()
            )
    finally:
        await engine.dispose()

    assert len(rows) == 1
    assert rows[0].resource_id is None
    assert rows[0].resource_type == "first-run"
    assert rows[0].detail == {"status_code": 201}
