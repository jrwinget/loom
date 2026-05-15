"""regression guard for the lite-profile schema bootstrap.

a fresh desktop-lite install ships an empty sqlite file: alembic
migrations only run via ``make migrate`` on server-profile, and
nothing in the bundled sidecar entrypoint creates tables. once the
frontend routes its requests to the sidecar, ``/first-run/status``
issues ``SELECT COUNT(*) FROM users`` and 500s on a missing table.

these tests pin two contracts:

  - calling the bootstrap against a fresh sqlite URL creates the
    full schema, so ``/first-run/status`` returns 200 with
    ``first_run_required=True``,
  - calling it with the server profile is a no-op, so the docker
    deployment's externally-managed migrations stay authoritative.
"""

from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path
from typing import Any
from unittest.mock import patch

import httpx
import pytest
from sqlalchemy.ext.asyncio import create_async_engine

from loom.__main__ import bootstrap_schema_if_lite
from loom.config import Settings, get_settings
from loom.dependencies import get_db_session
from loom.security.rate_limit import limiter


@pytest.fixture(autouse=True)
def _reset_rate_limiter() -> None:
    limiter.reset()


@pytest.fixture
def _lite_settings(tmp_path: Path) -> Settings:
    db_path = tmp_path / "loom.db"
    return Settings(
        secret_key="test-secret-key-that-is-long-enough-for-validation",
        database_url=f"sqlite+aiosqlite:///{db_path}",
        deployment_profile="lite",
        data_dir=tmp_path,
        storage_signing_secret="test-signing-secret",
    )


def _users_table_exists(db_path: Path) -> bool:
    """check the schema directly via the stdlib sqlite3 driver.

    avoid sqlalchemy's async engine here: the bootstrap calls
    ``asyncio.run`` inside alembic's env.py, which conflicts with an
    outer pytest-asyncio loop. a plain sync check sidesteps the
    nested-loop trap and isolates the schema assertion from the
    test runner's loop policy.
    """
    if not db_path.exists():
        return False
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='users'"
        ).fetchone()
        return row is not None
    finally:
        conn.close()


def _db_file(database_url: str) -> Path:
    return Path(database_url.split("///", 1)[1])


def test_bootstrap_creates_users_table_on_lite_profile(
    _lite_settings: Settings,
) -> None:
    """fresh sqlite + lite profile -> full schema is materialised."""
    db_path = _db_file(_lite_settings.database_url)
    assert not _users_table_exists(db_path)

    get_settings.cache_clear()
    with patch("loom.config.get_settings", return_value=_lite_settings):
        bootstrap_schema_if_lite()

    assert db_path.exists(), f"sqlite file missing: {db_path}"
    assert _users_table_exists(db_path), (
        f"users table missing in {db_path} (size={db_path.stat().st_size})"
    )


def test_bootstrap_seeds_alembic_version(
    _lite_settings: Settings,
) -> None:
    """alembic_version must be seeded so future migrations resume.

    without this row, a follow-up ``alembic upgrade head`` would try
    to replay every revision against the already-populated schema
    and crash on the first ``CREATE TABLE users`` (it already exists).
    """
    db_path = _db_file(_lite_settings.database_url)
    get_settings.cache_clear()
    with patch("loom.config.get_settings", return_value=_lite_settings):
        bootstrap_schema_if_lite()

    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute("SELECT version_num FROM alembic_version").fetchone()
    finally:
        conn.close()
    assert row is not None, "alembic_version row missing"
    assert isinstance(row[0], str) and row[0], "version_num must be non-empty"


def test_bootstrap_is_idempotent_on_existing_install(
    _lite_settings: Settings,
) -> None:
    """re-running on a populated db must not raise or duplicate state.

    every desktop launch invokes the bootstrap; the second-and-later
    runs must observe the existing schema, leave it alone, and keep
    alembic_version at one row.
    """
    db_path = _db_file(_lite_settings.database_url)
    get_settings.cache_clear()
    with patch("loom.config.get_settings", return_value=_lite_settings):
        bootstrap_schema_if_lite()
        bootstrap_schema_if_lite()

    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute("SELECT COUNT(*) FROM alembic_version").fetchone()
    finally:
        conn.close()
    assert rows == (1,)


def test_bootstrap_is_noop_on_server_profile(tmp_path: Path) -> None:
    """server profile must not touch the database.

    production postgres runs migrations out-of-band; auto-bootstrap
    from a sidecar binary that nobody runs in server deployments
    would be at best surprising and at worst unsafe.
    """
    server_settings = Settings(
        secret_key="test-secret-key-that-is-long-enough-for-validation",
        database_url="postgresql+asyncpg://loom:loom_dev@localhost:5432/loom",
        deployment_profile="server",
    )

    get_settings.cache_clear()
    with (
        patch("loom.config.get_settings", return_value=server_settings),
        patch("loom.__main__._bootstrap_sqlite_schema") as mock_create,
        patch("loom.__main__._stamp_alembic_head") as mock_stamp,
    ):
        bootstrap_schema_if_lite()

    mock_create.assert_not_called()
    mock_stamp.assert_not_called()


def test_bootstrap_creates_missing_data_dir(tmp_path: Path) -> None:
    """the data dir is created if absent before opening the engine.

    on a fresh install the tauri shell hands LOOM_DATA_DIR but does
    not pre-create it; sqlite raises ``unable to open database file``
    if the parent path does not exist when the engine connects.
    """
    data_dir = tmp_path / "fresh-install" / "loom-data"
    assert not data_dir.exists()
    db_path = data_dir / "loom.db"
    cfg = Settings(
        secret_key="test-secret-key-that-is-long-enough-for-validation",
        database_url=f"sqlite+aiosqlite:///{db_path}",
        deployment_profile="lite",
        data_dir=data_dir,
        storage_signing_secret="test-signing-secret",
    )

    get_settings.cache_clear()
    with patch("loom.config.get_settings", return_value=cfg):
        bootstrap_schema_if_lite()

    assert data_dir.is_dir()
    assert _users_table_exists(db_path)


def test_first_run_status_returns_200_after_bootstrap(
    _lite_settings: Settings,
) -> None:
    """end-to-end guard: status endpoint works on a freshly bootstrapped db.

    this is the test that would have caught the v0.1.3 outage: once
    the frontend reaches the sidecar, the first request is GET
    /first-run/status. without the bootstrap it 500s; with it, the
    desktop ``first_run_required`` path lights up correctly.
    """
    get_settings.cache_clear()
    with patch("loom.config.get_settings", return_value=_lite_settings):
        bootstrap_schema_if_lite()

        # build the app *after* settings are patched and the schema is in
        # place so the lifespan picks up the right database url.
        from loom.main import create_app

        application = create_app()

        async def override_db() -> Any:
            from sqlalchemy.ext.asyncio import (
                AsyncSession,
                async_sessionmaker,
            )

            engine = create_async_engine(_lite_settings.database_url)
            try:
                factory = async_sessionmaker(
                    engine,
                    class_=AsyncSession,
                    expire_on_commit=False,
                )
                async with factory() as session:
                    yield session
            finally:
                await engine.dispose()

        application.dependency_overrides[get_db_session] = override_db
        # the audit middleware reads app.state.db_session_factory and
        # bails when it's None — fine for this regression guard which
        # only exercises the /first-run/status read path.
        application.state.db_session_factory = None

        async def _run() -> httpx.Response:
            with patch(
                "loom.api.v1.first_run.get_settings",
                return_value=_lite_settings,
            ):
                async with httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=application),
                    base_url="http://testserver",
                ) as ac:
                    return await ac.get("/api/v1/first-run/status")

        # the bootstrap above used a sync alembic upgrade (with its
        # own asyncio.run inside env.py); run the http probe in a
        # fresh loop so the two stages don't trip the nested-loop
        # guard.
        resp = asyncio.run(_run())

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["first_run_required"] is True
    assert body["deployment_profile"] == "lite"
