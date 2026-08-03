"""Backfill assets.capture_time from extracted metadata

Revision ID: 021
Revises: 020
Create Date: 2026-07-24

ingest collected the container creation time into
metadata_extracted["capture_time_utc"] but never promoted it to the
typed capture_time column, so clustering, correlation, geo, and
court-bundle exhibit ordering all filtered on an always-NULL column.
the extraction activity now promotes the value at ingest time; this
migration fills the column for rows ingested before the fix.
lite-profile installs are the motivating case: their assets' capture
time sits only in metadata_extracted, so without this backfill every
pre-fix asset stays invisible to the time-based features.

replay-safe and idempotent by construction: only rows with
capture_time IS NULL are touched, so re-running is a no-op, and an
empty assets table (the smoke rewind case) short-circuits.
"""

import json
import re
from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

revision: str = "021"
down_revision: str | None = "020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_BATCH_SIZE = 500

# fractional seconds beyond microseconds, e.g. ".123456789"
_EXTRA_FRACTION = re.compile(r"(\.\d{6})\d+")


def _parse_capture_time(payload: object) -> datetime | None:
    """parse metadata_extracted's capture_time_utc to naive utc.

    the timestamp handling is an intentionally frozen copy of
    loom.services.clock_drift.parse_metadata_timestamp — migrations
    must not import app code that can drift after the revision is
    cut. sqlite drivers may hand the json column back as a str, so
    both dict and str payloads are accepted.
    """
    if isinstance(payload, bytes):
        try:
            payload = payload.decode("utf-8")
        except UnicodeDecodeError:
            return None
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except ValueError:
            return None
    if not isinstance(payload, dict):
        return None
    value = payload.get("capture_time_utc")
    if not isinstance(value, str) or not value.strip():
        return None
    raw = value.strip().replace("Z", "+00:00")
    raw = _EXTRA_FRACTION.sub(r"\1", raw)
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    # the column is timezone-naive utc
    return dt.astimezone(UTC).replace(tzinfo=None)


def upgrade() -> None:
    bind = op.get_bind()
    assets = sa.table(
        "assets",
        sa.column("id"),
        sa.column("capture_time", sa.DateTime()),
        sa.column("metadata_extracted", sa.JSON()),
    )

    # keyset pagination on the primary key so large installs never
    # load every row at once; rows whose payload fails to parse stay
    # NULL and are strictly skipped by the id cursor.
    last_id: object | None = None
    while True:
        query = (
            sa.select(assets.c.id, assets.c.metadata_extracted)
            .where(
                assets.c.capture_time.is_(None),
                assets.c.metadata_extracted.is_not(None),
            )
            .order_by(assets.c.id)
            .limit(_BATCH_SIZE)
        )
        if last_id is not None:
            query = query.where(assets.c.id > last_id)
        rows = bind.execute(query).fetchall()
        if not rows:
            break
        for row_id, payload in rows:
            capture_time = _parse_capture_time(payload)
            if capture_time is None:
                continue
            bind.execute(
                sa.update(assets)
                .where(assets.c.id == row_id)
                .values(capture_time=capture_time)
            )
        last_id = rows[-1][0]


def downgrade() -> None:
    # a backfill cannot be meaningfully reversed: nulling values a
    # user may since have verified would destroy evidence data
    pass
