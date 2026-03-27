"""tests for export activity implementations."""

import inspect
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest

from loom.workflows.export_activities import build_export

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
