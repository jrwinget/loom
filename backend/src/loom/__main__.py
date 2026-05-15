"""server entrypoint for the desktop sidecar.

separated from ``loom.main`` (the asgi factory) so that the docker
image and ``make dev`` can keep importing ``loom.main:app`` directly
while pyinstaller bundles this file as the binary's ``__main__``.
the desktop shell at desktop/src-tauri/src/main.rs polls
``http://127.0.0.1:8000/api/v1/health`` after spawning the sidecar,
so the host/port pair below is load-bearing -- changing it without
updating the rust side leaves the shell waiting on a dead endpoint.

passing the asgi callable as an object (not the ``loom.main:app``
import string) is deliberate: pyinstaller --onefile freezes the
module graph and uvicorn's string-import resolution does not
survive that, while a direct reference does.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
import threading
import time
from pathlib import Path
from urllib.parse import urlparse

import uvicorn
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.ext.asyncio import create_async_engine

import loom.config
from loom.main import app

# importing the models package for its side effect: each module
# registers tables against ``Base.metadata`` at import time, which is
# what ``create_all`` then materialises against sqlite.
from loom.models import *  # noqa: F403
from loom.models.base import Base

logger = logging.getLogger(__name__)

# how often the orphan watchdog polls getppid(). 1s is fast enough
# that the operator never sees a stale port-bind error on the next
# launch and slow enough to stay invisible in process listings.
_WATCHDOG_INTERVAL_SECONDS = 1.0


def _start_orphan_watchdog() -> None:
    """exit when the parent process dies.

    pyinstaller --onefile spawns the python interpreter as a child of
    a small bootloader. when the tauri shell calls ``child.kill()``
    against the externalBin it terminates the bootloader; the python
    process is orphaned (reparented to pid 1 on unix) and continues
    to hold ``127.0.0.1:8000``, blocking the next launch.

    this thread catches that case by polling ``os.getppid()`` and
    exiting when the original parent goes away. it is gated on
    ``LOOM_SHUTDOWN_TOKEN`` being set, which the desktop shell does
    on every launch — direct invocations (``nohup loom-backend &``,
    systemd, ``make dev``) get the env unset and skip the watchdog,
    so a backgrounded server doesn't self-terminate when its launching
    shell exits.

    windows installs are covered by the job-object the rust side
    attaches to the bootloader pid, so the watchdog is a unix-only
    safety net.
    """
    if sys.platform == "win32":
        return
    if not os.environ.get("LOOM_SHUTDOWN_TOKEN"):
        return

    initial_ppid = os.getppid()
    if initial_ppid <= 1:
        # already orphaned at startup (rare; e.g. a debugger launch)
        # — installing the watchdog would just exit immediately. let
        # the operator keep the process they meant to start.
        return

    def _watch() -> None:
        while True:
            time.sleep(_WATCHDOG_INTERVAL_SECONDS)
            current = os.getppid()
            if current == 1 or current != initial_ppid:
                # parent died — release port 8000 so the desktop
                # shell can respawn cleanly on the next launch.
                os._exit(0)

    thread = threading.Thread(
        target=_watch,
        daemon=True,
        name="loom-orphan-watchdog",
    )
    thread.start()


def _resolve_alembic_paths() -> tuple[Path, Path]:
    """return ``(alembic_ini, alembic_dir)`` for the current runtime.

    pyinstaller --onefile unpacks ``--add-data`` payloads into a
    per-process temp directory exposed as ``sys._MEIPASS`` (see the
    pyinstaller runtime docs). when frozen we look for the bundled
    copy there; when running from the source tree we walk up from
    this file to find the canonical ``backend/alembic.ini``.
    """
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass is not None:
        root = Path(meipass)
        return root / "alembic.ini", root / "alembic"
    # source layout: backend/src/loom/__main__.py -> backend/
    backend_root = Path(__file__).resolve().parents[2]
    return backend_root / "alembic.ini", backend_root / "alembic"


def _sqlite_db_path(database_url: str) -> Path | None:
    """extract the on-disk path from a sqlite URL, or None if N/A."""
    if not database_url.startswith(("sqlite+", "sqlite:")):
        return None
    # sqlalchemy URLs use 'sqlite+aiosqlite:///absolute/path/loom.db'
    # — three slashes for an absolute path on unix, four for windows
    # drive letters. urlparse handles both consistently.
    parsed = urlparse(database_url)
    raw = parsed.path
    if not raw:
        return None
    # urlparse leaves the leading slash; strip exactly one so an
    # absolute unix path stays absolute and a windows path like
    # ``/C:/loom/loom.db`` becomes ``C:/loom/loom.db``.
    if sys.platform == "win32" and len(raw) > 3 and raw[2] == ":":
        raw = raw.lstrip("/")
    if raw in {":memory:", "/:memory:"}:
        return None
    return Path(raw)


def _alembic_head_revision() -> str:
    """return the head revision id from the bundled alembic dir."""
    _, alembic_dir = _resolve_alembic_paths()
    script = ScriptDirectory(str(alembic_dir))
    head = script.get_current_head()
    if head is None:
        raise RuntimeError("alembic script directory has no head revision")
    return head


async def _bootstrap_sqlite_schema(database_url: str) -> None:
    """create the sqlite schema from sqlalchemy metadata, idempotently.

    we use ``Base.metadata.create_all`` rather than ``alembic upgrade``
    here because several of the historical migrations call
    ``op.add_column`` with a foreign-key constraint, which the sqlite
    dialect rejects ("No support for ALTER of constraints" — alembic
    requires its batch_alter_table escape hatch and the migrations
    were authored against postgres). a fresh lite install has no
    history to preserve, so we materialise the current model state
    in one shot; the caller seeds ``alembic_version`` separately so
    future migrations have a starting point. if the tables already
    exist the call is a no-op (create_all checks-and-skips per-table).
    """
    engine = create_async_engine(database_url)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    finally:
        await engine.dispose()


def _stamp_alembic_head(settings: loom.config.Settings) -> None:
    """write the alembic head revision into ``alembic_version``, if absent.

    server-profile docker images already run ``alembic upgrade head``
    out-of-band and the table is populated. on a fresh lite install
    we laid the schema down via ``metadata.create_all``, so we seed
    ``alembic_version`` directly with the head id; otherwise future
    migrations would try to replay every revision from scratch.

    we avoid ``alembic command.stamp`` because that re-exec's env.py
    which calls ``asyncio.run`` and conflicts with the running loop
    when the bootstrap is invoked from an async test fixture. a
    direct sql write against the well-known ``alembic_version``
    table is portable and dependency-free.
    """
    sync_url = settings.database_url.replace("sqlite+aiosqlite", "sqlite")

    engine = create_engine(sync_url)
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    "CREATE TABLE IF NOT EXISTS alembic_version ("
                    "version_num VARCHAR(32) NOT NULL PRIMARY KEY)"
                )
            )
            existing = conn.execute(
                text("SELECT version_num FROM alembic_version")
            ).first()
            if existing is not None:
                return
            conn.execute(
                text("INSERT INTO alembic_version (version_num) VALUES (:rev)"),
                {"rev": _alembic_head_revision()},
            )
    finally:
        engine.dispose()


def bootstrap_schema_if_lite() -> None:
    """materialise the lite-profile sqlite schema on first launch.

    desktop-lite installs ship a fresh ``loom.db`` with no tables.
    nothing on the server-profile / docker path needs this: those
    deployments manage migrations out-of-band via ``make migrate``,
    so gating on ``LOOM_DEPLOYMENT_PROFILE == "lite"`` keeps the
    sidecar binary's runtime self-bootstrapping and the dockerized
    deploy authoritative for production schema changes.

    the call is idempotent: ``create_all`` skips tables that already
    exist, and ``stamp`` is gated on an empty alembic_version table.
    """
    # call through the module so test patches on
    # ``loom.config.get_settings`` are honoured (a direct ``from
    # loom.config import get_settings`` binding would not pick up
    # mocks installed at test time).
    settings = loom.config.get_settings()
    if not settings.is_lite:
        return

    # ensure the data dir exists before sqlite opens the file. the
    # tauri shell sets LOOM_DATA_DIR but does not pre-create it on a
    # fresh install; aiosqlite then raises ``unable to open database
    # file`` and the boot gate stays red forever.
    data_dir = settings.resolved_data_dir()
    data_dir.mkdir(parents=True, exist_ok=True)

    db_path = _sqlite_db_path(settings.database_url)
    if db_path is not None:
        db_path.parent.mkdir(parents=True, exist_ok=True)

    logger.info("bootstrapping lite schema at %s", settings.database_url)
    asyncio.run(_bootstrap_sqlite_schema(settings.database_url))

    # log the inspected table list so a botched install surfaces in
    # the operator's journalctl output, not just as an opaque 500
    # later.
    sync_url = settings.database_url.replace("sqlite+aiosqlite", "sqlite")
    inspector_engine = create_engine(sync_url)
    try:
        tables = inspect(inspector_engine).get_table_names()
    finally:
        inspector_engine.dispose()
    logger.info("lite schema tables: %s", sorted(tables))

    _stamp_alembic_head(settings)


def main() -> None:
    _start_orphan_watchdog()
    bootstrap_schema_if_lite()
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=8000,
        log_config=None,
    )


if __name__ == "__main__":
    main()
