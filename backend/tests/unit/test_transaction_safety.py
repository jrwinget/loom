"""unit tests for transaction safety and savepoint behavior.

verifies that multi-step service operations use savepoints
for atomicity, and that the session dependency rolls back
on exceptions.
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from loom.dependencies import get_db_session
from loom.models.case import Case, CaseMembership
from loom.models.organization import (
    Organization,
    OrganizationMembership,
)
from loom.models.duplicate import (
    DuplicateCluster,
    DuplicateClusterMember,
)
from loom.services.case import create_case
from loom.services.organization import create_org
from loom.services.duplicate_detection import create_cluster
from loom.models.asset import Asset
from loom.services.ingest import create_asset_with_custody

_USER_ID = str(uuid4())
_CASE_ID = str(uuid4())
_ASSET_ID = uuid4()


def _mock_session() -> AsyncMock:
    """build a mock async session with savepoint support."""
    s = AsyncMock()
    s.add = MagicMock()
    s.commit = AsyncMock()
    s.flush = AsyncMock()
    s.refresh = AsyncMock()
    s.delete = AsyncMock()
    s.rollback = AsyncMock()

    # mock begin_nested() as async context manager
    nested_cm = AsyncMock()
    nested_cm.__aenter__ = AsyncMock(return_value=None)
    nested_cm.__aexit__ = AsyncMock(return_value=False)
    s.begin_nested = MagicMock(return_value=nested_cm)

    return s


# ── get_db_session rollback ────────────────────────────────


class TestSessionRollback:
    @pytest.mark.asyncio
    async def test_yields_session(self) -> None:
        """dependency yields the session normally."""
        mock_session = AsyncMock()
        mock_session.rollback = AsyncMock()
        mock_factory = MagicMock()

        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(
            return_value=mock_session
        )
        mock_cm.__aexit__ = AsyncMock(return_value=False)
        mock_factory.return_value = mock_cm

        mock_request = MagicMock()
        mock_request.app.state.db_session_factory = (
            mock_factory
        )

        gen = get_db_session(mock_request)
        session = await gen.__anext__()
        assert session is mock_session

    @pytest.mark.asyncio
    async def test_rollback_on_exception(self) -> None:
        """session.rollback called when exception propagates."""
        mock_session = AsyncMock()
        mock_session.rollback = AsyncMock()
        mock_factory = MagicMock()

        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(
            return_value=mock_session
        )
        mock_cm.__aexit__ = AsyncMock(return_value=False)
        mock_factory.return_value = mock_cm

        mock_request = MagicMock()
        mock_request.app.state.db_session_factory = (
            mock_factory
        )

        gen = get_db_session(mock_request)
        await gen.__anext__()

        # simulate an exception being thrown into the generator
        with pytest.raises(ValueError):
            await gen.athrow(ValueError("boom"))

        mock_session.rollback.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_exception_re_raised(self) -> None:
        """original exception is not swallowed."""
        mock_session = AsyncMock()
        mock_session.rollback = AsyncMock()
        mock_factory = MagicMock()

        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(
            return_value=mock_session
        )
        mock_cm.__aexit__ = AsyncMock(return_value=False)
        mock_factory.return_value = mock_cm

        mock_request = MagicMock()
        mock_request.app.state.db_session_factory = (
            mock_factory
        )

        gen = get_db_session(mock_request)
        await gen.__anext__()

        with pytest.raises(RuntimeError, match="test error"):
            await gen.athrow(RuntimeError("test error"))


# ── create_case savepoint ──────────────────────────────────


class TestCreateCaseSavepoint:
    @pytest.mark.asyncio
    async def test_uses_savepoint(self) -> None:
        """create_case wraps writes in begin_nested."""
        session = _mock_session()
        await create_case(session, "Test", "desc", _USER_ID)
        session.begin_nested.assert_called_once()

    @pytest.mark.asyncio
    async def test_adds_case_and_membership(self) -> None:
        """both case and membership are added."""
        session = _mock_session()
        result = await create_case(
            session, "Test", "desc", _USER_ID
        )
        assert isinstance(result, Case)
        assert session.add.call_count == 2
        # first add is the case
        first_add = session.add.call_args_list[0][0][0]
        assert isinstance(first_add, Case)
        # second add is the membership
        second_add = session.add.call_args_list[1][0][0]
        assert isinstance(second_add, CaseMembership)
        assert second_add.role == "owner"

    @pytest.mark.asyncio
    async def test_commits_after_savepoint(self) -> None:
        """commit happens after the savepoint block."""
        session = _mock_session()
        await create_case(session, "Test", None, _USER_ID)
        session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_savepoint_failure_prevents_commit(
        self,
    ) -> None:
        """if savepoint raises, commit is never called."""
        session = _mock_session()
        nested_cm = AsyncMock()
        nested_cm.__aenter__ = AsyncMock(return_value=None)
        nested_cm.__aexit__ = AsyncMock(return_value=False)
        # make flush raise inside the savepoint
        session.flush = AsyncMock(
            side_effect=RuntimeError("db error")
        )
        session.begin_nested = MagicMock(
            return_value=nested_cm
        )

        with pytest.raises(RuntimeError, match="db error"):
            await create_case(
                session, "Test", None, _USER_ID
            )

        session.commit.assert_not_awaited()


# ── create_org savepoint ───────────────────────────────────


class TestCreateOrgSavepoint:
    @pytest.mark.asyncio
    async def test_uses_savepoint(self) -> None:
        """create_org wraps writes in begin_nested."""
        session = _mock_session()
        await create_org(
            session, "NLG Portland", None, _USER_ID
        )
        session.begin_nested.assert_called_once()

    @pytest.mark.asyncio
    async def test_adds_org_and_membership(self) -> None:
        """both org and membership are added."""
        session = _mock_session()
        result = await create_org(
            session, "NLG Portland", "chapter", _USER_ID
        )
        assert isinstance(result, Organization)
        assert session.add.call_count == 2
        second_add = session.add.call_args_list[1][0][0]
        assert isinstance(second_add, OrganizationMembership)
        assert second_add.role == "admin"


# ── create_cluster savepoint ──────────────────────────────


class TestCreateClusterSavepoint:
    @pytest.mark.asyncio
    async def test_uses_savepoint(self) -> None:
        """create_cluster wraps writes in begin_nested."""
        session = _mock_session()
        aids = [str(uuid4()), str(uuid4())]
        phashes = {aids[0]: "abcd1234abcd1234", aids[1]: ""}
        await create_cluster(session, _CASE_ID, aids, phashes)
        session.begin_nested.assert_called_once()

    @pytest.mark.asyncio
    async def test_adds_cluster_and_members(self) -> None:
        """cluster + all members are added."""
        session = _mock_session()
        aids = [str(uuid4()), str(uuid4()), str(uuid4())]
        phashes = {a: "" for a in aids}
        result = await create_cluster(
            session, _CASE_ID, aids, phashes
        )
        assert isinstance(result, DuplicateCluster)
        # 1 cluster + 3 members = 4 add calls
        assert session.add.call_count == 4

    @pytest.mark.asyncio
    async def test_no_trailing_flush(self) -> None:
        """savepoint handles flush; no extra flush after."""
        session = _mock_session()
        aids = [str(uuid4())]
        phashes = {aids[0]: ""}
        await create_cluster(session, _CASE_ID, aids, phashes)
        # only the flush inside the savepoint for the cluster
        assert session.flush.await_count == 1


# ── create_asset_with_custody savepoint ───────────────────


def _mock_asset() -> Asset:
    """create a mock asset with a real uuid id."""
    asset = Asset(
        case_id=_ASSET_ID,
        original_filename="photo.jpg",
        storage_key="key/photo.jpg",
        media_type="image",
        mime_type="image/jpeg",
        file_size_bytes=1024,
        sha256_hash="sha256abc",
        sha512_hash="sha512def",
        upload_status="complete",
        uploaded_by=_ASSET_ID,
        processing_status="pending",
    )
    asset.id = _ASSET_ID
    return asset


class TestCreateAssetWithCustodySavepoint:
    @pytest.mark.asyncio
    @patch("loom.services.ingest.record_upload_custody")
    @patch("loom.services.ingest.create_asset_record")
    async def test_uses_savepoint(
        self,
        mock_create: AsyncMock,
        mock_custody: AsyncMock,
    ) -> None:
        """atomic helper wraps asset + custody in begin_nested."""
        session = _mock_session()
        mock_create.return_value = _mock_asset()
        mock_custody.return_value = None

        await create_asset_with_custody(
            session,
            _CASE_ID,
            "photo.jpg",
            "key/photo.jpg",
            "image",
            "image/jpeg",
            1024,
            "sha256abc",
            "sha512def",
            _USER_ID,
            "127.0.0.1",
        )
        session.begin_nested.assert_called_once()

    @pytest.mark.asyncio
    @patch("loom.services.ingest.record_upload_custody")
    @patch("loom.services.ingest.create_asset_record")
    async def test_calls_both_functions(
        self,
        mock_create: AsyncMock,
        mock_custody: AsyncMock,
    ) -> None:
        """both create_asset_record and record_upload_custody called."""
        session = _mock_session()
        mock_create.return_value = _mock_asset()
        mock_custody.return_value = None

        await create_asset_with_custody(
            session,
            _CASE_ID,
            "photo.jpg",
            "key/photo.jpg",
            "image",
            "image/jpeg",
            1024,
            "sha256abc",
            "sha512def",
            _USER_ID,
            None,
        )
        mock_create.assert_awaited_once()
        mock_custody.assert_awaited_once()

    @pytest.mark.asyncio
    @patch("loom.services.ingest.record_upload_custody")
    @patch("loom.services.ingest.create_asset_record")
    async def test_custody_failure_prevents_return(
        self,
        mock_create: AsyncMock,
        mock_custody: AsyncMock,
    ) -> None:
        """if custody write fails, exception propagates."""
        session = _mock_session()
        mock_create.return_value = _mock_asset()
        mock_custody.side_effect = RuntimeError(
            "custody write failed"
        )

        with pytest.raises(RuntimeError, match="custody"):
            await create_asset_with_custody(
                session,
                _CASE_ID,
                "photo.jpg",
                "key/photo.jpg",
                "image",
                "image/jpeg",
                1024,
                "sha256abc",
                "sha512def",
                _USER_ID,
                "127.0.0.1",
            )
