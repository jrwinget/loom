"""database engine helpers shared by the app and the workers."""

from typing import Any

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine


def _enable_sqlite_foreign_keys(dbapi_conn: Any, _record: Any) -> None:
    """turn on per-connection foreign-key enforcement for sqlite."""
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def install_sqlite_fk_enforcement(
    engine: AsyncEngine,
    database_url: str,
) -> None:
    """enable per-connection fk enforcement when the url is sqlite.

    sqlite (lite profile) enforces foreign keys only when asked, per
    connection; without this a case purge would orphan its assets
    and timeline instead of cascading. postgres enforces natively,
    so this is a no-op there.
    """
    if database_url.startswith("sqlite"):
        event.listen(
            engine.sync_engine,
            "connect",
            _enable_sqlite_foreign_keys,
        )
