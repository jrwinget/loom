"""tests for ingest activity implementations.

verifies that activities call the correct service methods
with the expected arguments and handle errors properly.
"""

import inspect
from unittest.mock import (
    AsyncMock,
    MagicMock,
    patch,
)
from uuid import UUID

import pytest

from loom.workflows.ingest_activities import (
    extract_asset_metadata,
    generate_asset_proxies,
    mark_asset_complete,
    record_derivatives_custody,
    verify_asset_hash,
)

_ASSET_ID = "01912345-6789-7abc-8def-0123456789ef"
_USER_ID = "01912345-6789-7abc-8def-012345678901"
_CASE_ID = "01912345-6789-7abc-8def-0123456789ab"


def _make_asset(
    *,
    media_type: str = "video",
    sha256: str = "abc123",
    sha512: str = "def456",
) -> MagicMock:
    """create a mock asset with sensible defaults."""
    asset = MagicMock()
    asset.id = UUID(_ASSET_ID)
    asset.case_id = UUID(_CASE_ID)
    asset.storage_key = f"{_CASE_ID}/{_ASSET_ID}/test.mp4"
    asset.original_filename = "test.mp4"
    asset.media_type = media_type
    asset.mime_type = "video/mp4"
    asset.sha256_hash = sha256
    asset.sha512_hash = sha512
    asset.uploaded_by = UUID(_USER_ID)
    asset.processing_status = "pending"
    asset.metadata_raw = None
    asset.metadata_extracted = None
    return asset


class TestActivityDecorators:
    """verify all activities have temporal decorators."""

    def test_verify_hash_is_activity(self) -> None:
        assert hasattr(
            verify_asset_hash,
            "__temporal_activity_definition",
        )

    def test_extract_metadata_is_activity(self) -> None:
        assert hasattr(
            extract_asset_metadata,
            "__temporal_activity_definition",
        )

    def test_generate_proxies_is_activity(self) -> None:
        assert hasattr(
            generate_asset_proxies,
            "__temporal_activity_definition",
        )

    def test_record_custody_is_activity(self) -> None:
        assert hasattr(
            record_derivatives_custody,
            "__temporal_activity_definition",
        )

    def test_mark_complete_is_activity(self) -> None:
        assert hasattr(
            mark_asset_complete,
            "__temporal_activity_definition",
        )

    def test_all_are_async(self) -> None:
        for fn in [
            verify_asset_hash,
            extract_asset_metadata,
            generate_asset_proxies,
            record_derivatives_custody,
            mark_asset_complete,
        ]:
            assert inspect.iscoroutinefunction(fn), (
                f"{fn.__name__} should be async"
            )


class TestVerifyAssetHash:
    """verify_asset_hash downloads and re-hashes."""

    @patch("loom.workflows.ingest_activities.get_minio_client")
    @patch("loom.workflows.ingest_activities.get_db_session")
    @patch("loom.workflows.ingest_activities.compute_hashes_from_file")
    async def test_returns_true_on_match(
        self,
        mock_hash: MagicMock,
        mock_session_ctx: MagicMock,
        mock_minio: MagicMock,
    ) -> None:
        """returns True when hashes match."""
        asset = _make_asset(sha256="aaa", sha512="bbb")

        session = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = asset
        session.execute.return_value = result

        ctx = AsyncMock()
        ctx.__aenter__.return_value = session
        mock_session_ctx.return_value = ctx

        mock_hash.return_value = ("aaa", "bbb")

        # mock storage download (no-op)
        mock_minio.return_value = MagicMock()

        with (
            patch("loom.workflows.ingest_activities.StorageService"),
            patch("loom.workflows.ingest_activities.tempfile") as mock_tmp,
        ):
            mock_tmp.TemporaryDirectory.return_value.__enter__ = (
                MagicMock(return_value="/tmp/test")  # noqa: S108
            )
            mock_tmp.TemporaryDirectory.return_value.__exit__ = MagicMock(
                return_value=False
            )
            result = await verify_asset_hash(_ASSET_ID)

        assert result is True

    @patch("loom.workflows.ingest_activities.get_minio_client")
    @patch("loom.workflows.ingest_activities.get_db_session")
    async def test_raises_on_missing_asset(
        self,
        mock_session_ctx: MagicMock,
        mock_minio: MagicMock,
    ) -> None:
        """raises ValueError when asset not found."""
        session = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        session.execute.return_value = result

        ctx = AsyncMock()
        ctx.__aenter__.return_value = session
        mock_session_ctx.return_value = ctx

        with pytest.raises(ValueError, match="not found"):
            await verify_asset_hash(_ASSET_ID)


class TestExtractAssetMetadata:
    """extract_asset_metadata calls service and stores result."""

    @patch("loom.workflows.ingest_activities.get_minio_client")
    @patch("loom.workflows.ingest_activities.get_db_session")
    @patch("loom.workflows.ingest_activities.extract_metadata_from_file")
    async def test_stores_metadata_on_asset(
        self,
        mock_extract: MagicMock,
        mock_session_ctx: MagicMock,
        mock_minio: MagicMock,
    ) -> None:
        """stores raw and normalized metadata."""
        asset = _make_asset()
        mock_extract.return_value = {
            "error": None,
            "raw": {"width": 1920},
            "normalized": {"width": 1920},
        }

        session = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = asset
        session.execute.return_value = result

        ctx = AsyncMock()
        ctx.__aenter__.return_value = session
        mock_session_ctx.return_value = ctx

        with (
            patch("loom.workflows.ingest_activities.StorageService"),
            patch("loom.workflows.ingest_activities.tempfile") as mock_tmp,
        ):
            mock_tmp.TemporaryDirectory.return_value.__enter__ = (
                MagicMock(return_value="/tmp/test")  # noqa: S108
            )
            mock_tmp.TemporaryDirectory.return_value.__exit__ = MagicMock(
                return_value=False
            )
            metadata = await extract_asset_metadata(_ASSET_ID)

        assert metadata["raw"] == {"width": 1920}
        session.commit.assert_awaited_once()


class TestMarkAssetComplete:
    """mark_asset_complete sets processing_status."""

    @patch("loom.workflows.ingest_activities.get_db_session")
    async def test_sets_status_complete(
        self,
        mock_session_ctx: MagicMock,
    ) -> None:
        """sets processing_status to complete."""
        asset = _make_asset()

        session = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = asset
        session.execute.return_value = result

        ctx = AsyncMock()
        ctx.__aenter__.return_value = session
        mock_session_ctx.return_value = ctx

        await mark_asset_complete(_ASSET_ID)

        assert asset.processing_status == "complete"
        session.commit.assert_awaited_once()

    @patch("loom.workflows.ingest_activities.get_db_session")
    async def test_raises_on_missing_asset(
        self,
        mock_session_ctx: MagicMock,
    ) -> None:
        """raises ValueError when asset not found."""
        session = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        session.execute.return_value = result

        ctx = AsyncMock()
        ctx.__aenter__.return_value = session
        mock_session_ctx.return_value = ctx

        with pytest.raises(ValueError, match="not found"):
            await mark_asset_complete(_ASSET_ID)


class TestRecordDerivativesCustody:
    """record_derivatives_custody creates chain entry."""

    @patch("loom.workflows.ingest_activities.get_db_session")
    async def test_creates_custody_entry(
        self,
        mock_session_ctx: MagicMock,
    ) -> None:
        """creates ingest_verified custody entry."""
        asset = _make_asset()

        session = AsyncMock()
        session.add = MagicMock()

        # first call returns asset, second returns no existing
        call_count = 0

        async def mock_execute(query: object) -> MagicMock:
            nonlocal call_count
            call_count += 1
            r = MagicMock()
            if call_count == 1:
                r.scalar_one_or_none.return_value = asset
            else:
                r.scalar_one_or_none.return_value = None
            return r

        session.execute = mock_execute

        ctx = AsyncMock()
        ctx.__aenter__.return_value = session
        mock_session_ctx.return_value = ctx

        await record_derivatives_custody(_ASSET_ID)

        session.add.assert_called_once()
        added = session.add.call_args[0][0]
        assert added.action == "ingest_verified"
        assert added.asset_id == UUID(_ASSET_ID)
        session.commit.assert_awaited_once()

    @patch("loom.workflows.ingest_activities.get_db_session")
    async def test_skips_if_already_recorded(
        self,
        mock_session_ctx: MagicMock,
    ) -> None:
        """does not duplicate if entry already exists."""
        asset = _make_asset()
        existing_entry = MagicMock()

        session = AsyncMock()
        session.add = MagicMock()
        call_count = 0

        async def mock_execute(query: object) -> MagicMock:
            nonlocal call_count
            call_count += 1
            r = MagicMock()
            if call_count == 1:
                r.scalar_one_or_none.return_value = asset
            else:
                # existing entry found
                r.scalar_one_or_none.return_value = existing_entry
            return r

        session.execute = mock_execute

        ctx = AsyncMock()
        ctx.__aenter__.return_value = session
        mock_session_ctx.return_value = ctx

        await record_derivatives_custody(_ASSET_ID)

        session.add.assert_not_called()
