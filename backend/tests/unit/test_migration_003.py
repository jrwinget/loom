"""Tests for migration 003: redactions and revoked_tokens tables."""

import importlib.util
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock, call

import pytest


def _load_migration() -> ModuleType:
    """load migration module from file path."""
    path = (
        Path(__file__).resolve().parents[2]
        / "alembic"
        / "versions"
        / "003_add_redactions_and_revoked_tokens.py"
    )
    spec = importlib.util.spec_from_file_location("migration_003", path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


migration = _load_migration()


def test_revision_identifiers() -> None:
    assert migration.revision == "003b"
    assert migration.down_revision == "003"


class TestUpgrade:
    """Verify upgrade creates both tables with correct DDL."""

    def test_creates_redactions_table(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        mock_op = MagicMock()
        monkeypatch.setattr(migration, "op", mock_op)
        monkeypatch.setattr(migration, "sa", _real_sa())

        migration.upgrade()

        table_calls = [
            c
            for c in mock_op.create_table.call_args_list
            if c[0][0] == "redactions"
        ]
        assert len(table_calls) == 1

        cols = _extract_column_names(table_calls[0])
        expected = {
            "id",
            "asset_id",
            "redacted_by",
            "redaction_type",
            "regions",
            "status",
            "output_storage_key",
            "error_message",
            "created_at",
            "updated_at",
        }
        assert cols == expected

    def test_creates_revoked_tokens_table(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        mock_op = MagicMock()
        monkeypatch.setattr(migration, "op", mock_op)
        monkeypatch.setattr(migration, "sa", _real_sa())

        migration.upgrade()

        table_calls = [
            c
            for c in mock_op.create_table.call_args_list
            if c[0][0] == "revoked_tokens"
        ]
        assert len(table_calls) == 1

        cols = _extract_column_names(table_calls[0])
        expected = {
            "id",
            "jti",
            "user_id",
            "revoked_at",
            "expires_at",
        }
        assert cols == expected

    def test_creates_indexes(self, monkeypatch: pytest.MonkeyPatch) -> None:
        mock_op = MagicMock()
        monkeypatch.setattr(migration, "op", mock_op)
        monkeypatch.setattr(migration, "sa", _real_sa())

        migration.upgrade()

        index_names = [c[0][0] for c in mock_op.create_index.call_args_list]
        assert "ix_redactions_asset_id" in index_names
        assert "ix_revoked_tokens_jti" in index_names
        assert "ix_revoked_tokens_user_id" in index_names

    def test_redactions_check_constraints(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        mock_op = MagicMock()
        monkeypatch.setattr(migration, "op", mock_op)
        monkeypatch.setattr(migration, "sa", _real_sa())

        migration.upgrade()

        redactions_call = next(
            c
            for c in mock_op.create_table.call_args_list
            if c[0][0] == "redactions"
        )

        import sqlalchemy as sa

        constraint_names = set()
        for arg in redactions_call[0][1:]:
            if isinstance(arg, sa.CheckConstraint):
                constraint_names.add(arg.name)
        assert "ck_redactions_type" in constraint_names
        assert "ck_redactions_status" in constraint_names


class TestDowngrade:
    """Verify downgrade drops both tables."""

    def test_drops_tables(self, monkeypatch: pytest.MonkeyPatch) -> None:
        mock_op = MagicMock()
        monkeypatch.setattr(migration, "op", mock_op)

        migration.downgrade()

        dropped = [c[0][0] for c in mock_op.drop_table.call_args_list]
        assert "revoked_tokens" in dropped
        assert "redactions" in dropped

    def test_drops_revoked_tokens_before_redactions(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        mock_op = MagicMock()
        monkeypatch.setattr(migration, "op", mock_op)

        migration.downgrade()

        dropped = [c[0][0] for c in mock_op.drop_table.call_args_list]
        assert dropped.index("revoked_tokens") < dropped.index("redactions")


def _real_sa() -> MagicMock:
    """return real sqlalchemy so Column/ForeignKey etc work."""
    import sqlalchemy as sa

    mock = MagicMock(wraps=sa)
    mock.func = sa.func
    # keep postgresql accessible for JSON column
    mock.__name__ = "sqlalchemy"
    return mock


def _extract_column_names(create_call: call) -> set[str]:
    """pull column names from a create_table mock call."""
    import sqlalchemy as sa

    names: set[str] = set()
    for arg in create_call[0][1:]:
        if isinstance(arg, sa.Column):
            names.add(arg.name)
    return names
