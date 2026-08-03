"""tests for export activity implementations."""

import inspect
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest

from loom.workflows.export_activities import (
    _build_court_bundle,
    _resolve_preparer,
    build_export,
)

_EXPORT_ID = "01912345-6789-7abc-8def-0123456789ab"
_CASE_ID = "01912345-6789-7abc-8def-0123456789ef"


def _make_export(
    fmt: str = "zip",
    status: str = "pending",
) -> MagicMock:
    """create a mock export bundle."""
    export = MagicMock()
    export.id = UUID(_EXPORT_ID)
    export.case_id = UUID(_CASE_ID)
    export.format = fmt
    export.status = status
    export.manifest = None
    export.storage_key = ""
    export.sha256_hash = ""
    return export


class TestBuildExportActivity:
    """build_export delegates to format-specific builders."""

    def test_is_temporal_activity(self) -> None:
        assert hasattr(
            build_export,
            "__temporal_activity_definition",
        )

    def test_is_async(self) -> None:
        assert inspect.iscoroutinefunction(build_export)

    @patch("loom.workflows.export_activities.get_db_session")
    async def test_returns_export_id_when_not_found(
        self,
        mock_session_ctx: MagicMock,
    ) -> None:
        """returns export_id when export record missing."""
        session = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        session.execute.return_value = result

        ctx = AsyncMock()
        ctx.__aenter__.return_value = session
        mock_session_ctx.return_value = ctx

        out = await build_export(_EXPORT_ID)
        assert out == _EXPORT_ID

    @patch("loom.workflows.export_activities._build_json_manifest")
    @patch("loom.workflows.export_activities.get_db_session")
    async def test_calls_json_builder_for_json_format(
        self,
        mock_session_ctx: MagicMock,
        mock_json_builder: AsyncMock,
    ) -> None:
        """dispatches to json manifest builder."""
        export = _make_export(fmt="json_manifest")
        mock_json_builder.return_value = None

        session = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = export
        session.execute.return_value = result

        ctx = AsyncMock()
        ctx.__aenter__.return_value = session
        mock_session_ctx.return_value = ctx

        await build_export(_EXPORT_ID)

        mock_json_builder.assert_awaited_once()
        assert export.status == "complete"

    @patch("loom.workflows.export_activities._build_zip_bundle")
    @patch("loom.workflows.export_activities.get_db_session")
    async def test_calls_zip_builder_for_zip_format(
        self,
        mock_session_ctx: MagicMock,
        mock_zip_builder: AsyncMock,
    ) -> None:
        """dispatches to zip bundle builder."""
        export = _make_export(fmt="zip")
        mock_zip_builder.return_value = None

        session = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = export
        session.execute.return_value = result

        ctx = AsyncMock()
        ctx.__aenter__.return_value = session
        mock_session_ctx.return_value = ctx

        await build_export(_EXPORT_ID)

        mock_zip_builder.assert_awaited_once()
        assert export.status == "complete"

    @patch("loom.workflows.export_activities._build_zip_bundle")
    @patch("loom.workflows.export_activities.get_db_session")
    async def test_marks_failed_on_error(
        self,
        mock_session_ctx: MagicMock,
        mock_zip_builder: AsyncMock,
    ) -> None:
        """sets status to failed when builder raises."""
        export = _make_export(fmt="zip")
        mock_zip_builder.side_effect = RuntimeError("boom")

        session = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = export
        session.execute.return_value = result

        ctx = AsyncMock()
        ctx.__aenter__.return_value = session
        mock_session_ctx.return_value = ctx

        with pytest.raises(RuntimeError, match="boom"):
            await build_export(_EXPORT_ID)

        assert export.status == "failed"

    @patch("loom.workflows.export_activities._build_zip_bundle")
    @patch("loom.workflows.export_activities.get_db_session")
    async def test_rolls_back_before_recording_failure(
        self,
        mock_session_ctx: MagicMock,
        mock_zip_builder: AsyncMock,
    ) -> None:
        """a failed build must not commit staged custody rows.

        custody is append-only — anything the builder session.add()ed
        before raising would otherwise be committed alongside the
        failed status and could never be removed.
        """
        export = _make_export(fmt="zip")
        mock_zip_builder.side_effect = RuntimeError("boom")

        session = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = export
        session.execute.return_value = result

        ctx = AsyncMock()
        ctx.__aenter__.return_value = session
        mock_session_ctx.return_value = ctx

        with pytest.raises(RuntimeError, match="boom"):
            await build_export(_EXPORT_ID)

        session.rollback.assert_awaited_once()
        session.add.assert_not_called()

    @patch("loom.workflows.export_activities._build_zip_bundle")
    @patch("loom.workflows.export_activities.get_db_session")
    async def test_writes_exported_custody_entries(
        self,
        mock_session_ctx: MagicMock,
        mock_zip_builder: AsyncMock,
    ) -> None:
        """each included original gets an exported custody entry in
        the same commit as the flip to complete."""
        export = _make_export(fmt="zip")
        export.name = "production set 1"
        export.sha256_hash = "c" * 64
        export.created_by = UUID(_CASE_ID)
        asset_id = UUID("00000000-0000-0000-0000-000000000042")
        mock_zip_builder.return_value = [
            {"id": str(asset_id), "sha256": "a" * 64}
        ]

        session = AsyncMock()
        session.add = MagicMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = export
        session.execute.return_value = result

        ctx = AsyncMock()
        ctx.__aenter__.return_value = session
        mock_session_ctx.return_value = ctx

        await build_export(_EXPORT_ID)

        session.add.assert_called_once()
        entry = session.add.call_args[0][0]
        assert entry.action == "exported"
        assert entry.actor_id == export.created_by
        assert entry.detail["export_id"] == _EXPORT_ID
        assert entry.detail["format"] == "zip"
        assert entry.detail["verified"] is True
        assert export.status == "complete"


def _session_returning_user(user: MagicMock | None) -> AsyncMock:
    session = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = user
    session.execute.return_value = result
    return session


class TestResolvePreparer:
    """the court-bundle cover and declaration must carry a human
    name, not the raw created_by uuid."""

    async def test_prefers_display_name(self) -> None:
        user = MagicMock()
        user.display_name = "Jane Analyst"
        user.email = "jane@example.org"
        session = _session_returning_user(user)

        name = await _resolve_preparer(session, UUID(_CASE_ID))
        assert name == "Jane Analyst"

    async def test_falls_back_to_email(self) -> None:
        user = MagicMock()
        user.display_name = ""
        user.email = "jane@example.org"
        session = _session_returning_user(user)

        name = await _resolve_preparer(session, UUID(_CASE_ID))
        assert name == "jane@example.org"

    async def test_falls_back_to_uuid_when_user_missing(self) -> None:
        session = _session_returning_user(None)

        name = await _resolve_preparer(session, UUID(_CASE_ID))
        assert name == _CASE_ID

    @patch("loom.services.streaming_upload.upload_tmp_dir")
    @patch("loom.config.get_settings")
    @patch("loom.workflows.export_activities.get_storage_backend")
    @patch(
        "loom.services.court_bundle.build_court_bundle",
        new_callable=AsyncMock,
    )
    async def test_court_bundle_builder_passes_resolved_name(
        self,
        mock_build: AsyncMock,
        mock_storage: MagicMock,
        mock_settings: MagicMock,
        mock_tmp_dir: MagicMock,
        tmp_path: Path,
    ) -> None:
        export = _make_export(fmt="court_bundle")
        export.created_by = UUID(_CASE_ID)
        export.options = {}

        user = MagicMock()
        user.display_name = "Jane Analyst"
        user.email = "jane@example.org"
        session = _session_returning_user(user)

        mock_build.return_value = ("f" * 64, [])
        mock_settings.return_value = MagicMock(bundle_signing_key=None)
        mock_tmp_dir.return_value = tmp_path

        await _build_court_bundle(session, export, _CASE_ID)

        assert mock_build.call_args.kwargs["preparer"] == "Jane Analyst"
