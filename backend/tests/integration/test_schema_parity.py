"""guard against drift between the two schema sources of truth.

the desktop sidecar materialises the schema with
``Base.metadata.create_all`` (alembic's add-column-with-fk migrations
don't run on sqlite without batch mode); the server runs alembic.
if the models and the alembic head disagree, the profiles silently
split. comparing the migrated postgres schema against the model
metadata proves models == alembic head, which implies lite == server
by construction.

runs inside the CI ``test-migrations`` job, after the
upgrade/downgrade round-trip, against its postgres service. skipped
everywhere else (the default test job runs on sqlite).
"""

from __future__ import annotations

import os
import re
from collections import Counter
from pathlib import Path

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy.ext.asyncio import create_async_engine

from loom.models import Base

_DB_URL = os.environ.get("LOOM_DATABASE_URL", "")

# expected diffs that are dialect noise, not drift. entries are
# substrings matched against the rendered diff line; keep this list
# empty unless a diff is UNDERSTOOD and provably harmless.
_ALLOWLIST: tuple[str, ...] = ()

_VERSIONS_DIR = Path(__file__).resolve().parents[2] / "alembic" / "versions"


def _is_allowed(rendered: str) -> bool:
    return any(marker in rendered for marker in _ALLOWLIST)


@pytest.mark.skipif(
    not _DB_URL.startswith("postgresql"),
    reason="schema parity is checked against the migrated postgres db",
)
@pytest.mark.asyncio
async def test_models_match_alembic_head() -> None:
    engine = create_async_engine(_DB_URL)
    try:
        async with engine.connect() as conn:
            diffs = await conn.run_sync(
                lambda sync_conn: compare_metadata(
                    MigrationContext.configure(
                        sync_conn,
                        opts={"compare_type": True},
                    ),
                    Base.metadata,
                )
            )
    finally:
        await engine.dispose()

    rendered = [repr(diff) for diff in diffs]
    violations = [line for line in rendered if not _is_allowed(line)]
    assert not violations, (
        "models and alembic head disagree — lite (create_all) and "
        "server (migrations) would diverge:\n  " + "\n  ".join(violations)
    )


def test_no_duplicate_migration_number_prefixes() -> None:
    """filenames are labels, revision ids are truth — but a duplicate
    numeric prefix invites picking the wrong file. the historical
    003 pair predates this guard and stays (shipped migrations are
    not renamed)."""
    allowed_duplicates = {"003"}
    prefixes = [
        match.group(1)
        for path in _VERSIONS_DIR.glob("*.py")
        if (match := re.match(r"^(\d+)_", path.name))
    ]
    duplicates = {
        prefix
        for prefix, count in Counter(prefixes).items()
        if count > 1 and prefix not in allowed_duplicates
    }
    assert not duplicates, (
        f"duplicate migration number prefix(es): {sorted(duplicates)}"
    )
