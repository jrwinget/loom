"""ORM-level append-only enforcement.

Evidence tables (``audit_log`` and ``chain_of_custody_entries``)
must be insert-only: any mutation or deletion is a tamper signal.
Postgres deployments also install database triggers via migration
011 so raw-SQL callers are blocked too; this module is the
portable belt that catches the ORM path on every profile,
including Desktop Lite (SQLite).
"""

from typing import Any

from sqlalchemy import event
from sqlalchemy.orm import Mapper


class AppendOnlyViolationError(RuntimeError):
    """raised when an append-only table receives UPDATE or DELETE."""


def _deny(verb: str, table: str) -> None:
    raise AppendOnlyViolationError(
        f"{table} is append-only: {verb} is not permitted"
    )


def enforce_append_only(model: type) -> None:
    """register before_update / before_delete listeners on ``model``.

    idempotent: safe to call at module import even if the same
    Base is imported twice.
    """
    table = model.__tablename__  # type: ignore[attr-defined]

    @event.listens_for(model, "before_update", propagate=True)
    def _on_update(
        _mapper: Mapper[Any],
        _connection: Any,
        _target: Any,
    ) -> None:
        _deny("UPDATE", table)

    @event.listens_for(model, "before_delete", propagate=True)
    def _on_delete(
        _mapper: Mapper[Any],
        _connection: Any,
        _target: Any,
    ) -> None:
        _deny("DELETE", table)
