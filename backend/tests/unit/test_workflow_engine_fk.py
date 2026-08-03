"""foreign-key enforcement on the shared workflows engine.

the fastapi app installs a per-connection ``PRAGMA
foreign_keys=ON`` listener for sqlite; the workflows engine must
do the same or lite-profile activities run with fk enforcement
off (a case purge would orphan its assets instead of cascading).
"""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from sqlalchemy import text

from loom.workflows import shared


@pytest.fixture(autouse=True)
def _reset_shared() -> None:
    """reset module caches before each test."""
    shared.reset_for_testing()


def _sqlite_settings(tmp_path: Path) -> SimpleNamespace:
    # a file-backed url, like the lite profile uses; :memory: would
    # switch sqlalchemy to a staticpool that rejects the pool args.
    return SimpleNamespace(
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'loom.db'}",
        db_pool_size=5,
        db_max_overflow=10,
        db_pool_recycle=3600,
        db_pool_pre_ping=True,
        db_pool_timeout=30,
    )


async def test_sqlite_connections_enforce_foreign_keys(
    tmp_path: Path,
) -> None:
    """every pooled sqlite connection must have fk enforcement on."""
    with patch(
        "loom.workflows.shared.get_settings",
        return_value=_sqlite_settings(tmp_path),
    ):
        engine = shared._get_engine()
        try:
            async with engine.connect() as conn:
                result = await conn.execute(text("PRAGMA foreign_keys"))
                assert result.scalar() == 1
        finally:
            await shared.dispose_engine()
