"""unit tests for loom.services.shared_evidence."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from loom.models.asset import Asset
from loom.models.organization import SharedEvidenceLink
from loom.services.shared_evidence import (
    check_shared_access,
    list_shared_from_case,
    list_shared_with_case,
    revoke_share,
    share_evidence,
)

_SOURCE_CASE = str(uuid4())
_TARGET_CASE = str(uuid4())
_ASSET_ID = str(uuid4())
_USER_ID = str(uuid4())
_LINK_ID = str(uuid4())


def _mock_session() -> AsyncMock:
    s = AsyncMock()
    s.add = MagicMock()
    s.commit = AsyncMock()
    s.refresh = AsyncMock()
    s.delete = AsyncMock()
    return s


# ── share_evidence ──────────────────────────────────────────


class TestShareEvidence:
    @pytest.mark.asyncio
    @patch("loom.services.shared_evidence.check_case_access")
    async def test_creates_share_link(self, mock_access: AsyncMock) -> None:
        """creates link when user has editor access and asset exists."""
        mock_access.return_value = True
        session = _mock_session()
        asset = Asset(
            case_id=UUID(_SOURCE_CASE),
            original_filename="video.mp4",
            storage_key="k",
            media_type="video",
            mime_type="video/mp4",
            file_size_bytes=1000,
            sha256_hash="a" * 64,
            sha512_hash="b" * 128,
            uploaded_by=UUID(_USER_ID),
        )
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = asset
        session.execute.return_value = mock_result

        result = await share_evidence(
            session,
            _SOURCE_CASE,
            _TARGET_CASE,
            _ASSET_ID,
            _USER_ID,
            access_level="annotate",
        )
        assert isinstance(result, SharedEvidenceLink)
        assert result.source_case_id == UUID(_SOURCE_CASE)
        assert result.target_case_id == UUID(_TARGET_CASE)
        assert result.asset_id == UUID(_ASSET_ID)
        assert result.access_level == "annotate"
        session.add.assert_called_once()
        session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    @patch("loom.services.shared_evidence.check_case_access")
    async def test_raises_permission_error(
        self, mock_access: AsyncMock
    ) -> None:
        """raises PermissionError when user lacks editor access."""
        mock_access.return_value = False
        session = _mock_session()

        with pytest.raises(PermissionError, match="insufficient access"):
            await share_evidence(
                session,
                _SOURCE_CASE,
                _TARGET_CASE,
                _ASSET_ID,
                _USER_ID,
            )

    @pytest.mark.asyncio
    @patch("loom.services.shared_evidence.check_case_access")
    async def test_raises_value_error_asset_not_found(
        self, mock_access: AsyncMock
    ) -> None:
        """raises ValueError when asset not in source case."""
        mock_access.return_value = True
        session = _mock_session()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute.return_value = mock_result

        with pytest.raises(ValueError, match="asset not found"):
            await share_evidence(
                session,
                _SOURCE_CASE,
                _TARGET_CASE,
                _ASSET_ID,
                _USER_ID,
            )

    @pytest.mark.asyncio
    @patch("loom.services.shared_evidence.check_case_access")
    async def test_default_access_level_view(
        self, mock_access: AsyncMock
    ) -> None:
        """access_level defaults to view."""
        mock_access.return_value = True
        session = _mock_session()
        asset = Asset(
            case_id=UUID(_SOURCE_CASE),
            original_filename="f",
            storage_key="k",
            media_type="image",
            mime_type="image/jpeg",
            file_size_bytes=100,
            sha256_hash="a" * 64,
            sha512_hash="b" * 128,
            uploaded_by=UUID(_USER_ID),
        )
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = asset
        session.execute.return_value = mock_result

        result = await share_evidence(
            session,
            _SOURCE_CASE,
            _TARGET_CASE,
            _ASSET_ID,
            _USER_ID,
        )
        assert result.access_level == "view"

    @pytest.mark.asyncio
    @patch("loom.services.shared_evidence.check_case_access")
    async def test_expires_at_stored(self, mock_access: AsyncMock) -> None:
        """expires_at is set when provided."""
        mock_access.return_value = True
        session = _mock_session()
        asset = Asset(
            case_id=UUID(_SOURCE_CASE),
            original_filename="f",
            storage_key="k",
            media_type="image",
            mime_type="image/jpeg",
            file_size_bytes=100,
            sha256_hash="a" * 64,
            sha512_hash="b" * 128,
            uploaded_by=UUID(_USER_ID),
        )
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = asset
        session.execute.return_value = mock_result

        expires = datetime(2026, 12, 31, tzinfo=UTC)
        result = await share_evidence(
            session,
            _SOURCE_CASE,
            _TARGET_CASE,
            _ASSET_ID,
            _USER_ID,
            expires_at=expires,
        )
        assert result.expires_at == expires


# ── list_shared_with_case ───────────────────────────────────


class TestListSharedWithCase:
    @pytest.mark.asyncio
    async def test_returns_links_with_filename(self) -> None:
        """attaches original_filename from joined asset row."""
        session = _mock_session()
        link = SharedEvidenceLink(
            source_case_id=UUID(_SOURCE_CASE),
            target_case_id=UUID(_TARGET_CASE),
            asset_id=UUID(_ASSET_ID),
            shared_by=UUID(_USER_ID),
        )
        row = MagicMock()
        row.__getitem__ = lambda self, i: [link, "evidence.mp4"][i]
        mock_result = MagicMock()
        mock_result.all.return_value = [row]
        session.execute.return_value = mock_result

        links = await list_shared_with_case(session, _TARGET_CASE)
        assert len(links) == 1
        assert links[0].original_filename == "evidence.mp4"

    @pytest.mark.asyncio
    async def test_empty_list(self) -> None:
        session = _mock_session()
        mock_result = MagicMock()
        mock_result.all.return_value = []
        session.execute.return_value = mock_result

        assert await list_shared_with_case(session, _TARGET_CASE) == []


# ── list_shared_from_case ───────────────────────────────────


class TestListSharedFromCase:
    @pytest.mark.asyncio
    async def test_returns_links_with_filename(self) -> None:
        session = _mock_session()
        link = SharedEvidenceLink(
            source_case_id=UUID(_SOURCE_CASE),
            target_case_id=UUID(_TARGET_CASE),
            asset_id=UUID(_ASSET_ID),
            shared_by=UUID(_USER_ID),
        )
        row = MagicMock()
        row.__getitem__ = lambda self, i: [link, "doc.pdf"][i]
        mock_result = MagicMock()
        mock_result.all.return_value = [row]
        session.execute.return_value = mock_result

        links = await list_shared_from_case(session, _SOURCE_CASE)
        assert len(links) == 1
        assert links[0].original_filename == "doc.pdf"

    @pytest.mark.asyncio
    async def test_empty_list(self) -> None:
        session = _mock_session()
        mock_result = MagicMock()
        mock_result.all.return_value = []
        session.execute.return_value = mock_result

        assert await list_shared_from_case(session, _SOURCE_CASE) == []


# ── revoke_share ────────────────────────────────────────────


class TestRevokeShare:
    @pytest.mark.asyncio
    @patch("loom.services.shared_evidence.check_case_access")
    async def test_revokes_existing_link(self, mock_access: AsyncMock) -> None:
        """returns true and deletes the link."""
        mock_access.return_value = True
        session = _mock_session()
        link = SharedEvidenceLink(
            source_case_id=UUID(_SOURCE_CASE),
            target_case_id=UUID(_TARGET_CASE),
            asset_id=UUID(_ASSET_ID),
            shared_by=UUID(_USER_ID),
        )
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = link
        session.execute.return_value = mock_result

        assert (
            await revoke_share(session, _LINK_ID, _SOURCE_CASE, _USER_ID)
            is True
        )
        session.delete.assert_awaited_once_with(link)

    @pytest.mark.asyncio
    async def test_returns_false_when_link_not_found(self) -> None:
        """returns false when link does not exist."""
        session = _mock_session()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute.return_value = mock_result

        assert (
            await revoke_share(session, _LINK_ID, _SOURCE_CASE, _USER_ID)
            is False
        )

    @pytest.mark.asyncio
    @patch("loom.services.shared_evidence.check_case_access")
    async def test_raises_when_no_editor_access(
        self, mock_access: AsyncMock
    ) -> None:
        """raises PermissionError if user lacks editor access."""
        mock_access.return_value = False
        session = _mock_session()
        link = SharedEvidenceLink(
            source_case_id=UUID(_SOURCE_CASE),
            target_case_id=UUID(_TARGET_CASE),
            asset_id=UUID(_ASSET_ID),
            shared_by=UUID(_USER_ID),
        )
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = link
        session.execute.return_value = mock_result

        with pytest.raises(PermissionError, match="insufficient access"):
            await revoke_share(session, _LINK_ID, _SOURCE_CASE, _USER_ID)


# ── check_shared_access ────────────────────────────────────


class TestCheckSharedAccess:
    @pytest.mark.asyncio
    async def test_returns_true_no_expiry(self) -> None:
        """returns true when link exists with no expiration."""
        session = _mock_session()
        link = SharedEvidenceLink(
            source_case_id=UUID(_SOURCE_CASE),
            target_case_id=UUID(_TARGET_CASE),
            asset_id=UUID(_ASSET_ID),
            shared_by=UUID(_USER_ID),
        )
        link.expires_at = None
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = link
        session.execute.return_value = mock_result

        assert (
            await check_shared_access(session, _ASSET_ID, _TARGET_CASE) is True
        )

    @pytest.mark.asyncio
    async def test_returns_true_future_expiry(self) -> None:
        """returns true when expiration is in the future."""
        session = _mock_session()
        link = SharedEvidenceLink(
            source_case_id=UUID(_SOURCE_CASE),
            target_case_id=UUID(_TARGET_CASE),
            asset_id=UUID(_ASSET_ID),
            shared_by=UUID(_USER_ID),
        )
        link.expires_at = datetime.now(tz=UTC) + timedelta(days=30)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = link
        session.execute.return_value = mock_result

        assert (
            await check_shared_access(session, _ASSET_ID, _TARGET_CASE) is True
        )

    @pytest.mark.asyncio
    async def test_returns_false_expired(self) -> None:
        """returns false when link has expired."""
        session = _mock_session()
        link = SharedEvidenceLink(
            source_case_id=UUID(_SOURCE_CASE),
            target_case_id=UUID(_TARGET_CASE),
            asset_id=UUID(_ASSET_ID),
            shared_by=UUID(_USER_ID),
        )
        link.expires_at = datetime.now(tz=UTC) - timedelta(days=1)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = link
        session.execute.return_value = mock_result

        assert (
            await check_shared_access(session, _ASSET_ID, _TARGET_CASE) is False
        )

    @pytest.mark.asyncio
    async def test_returns_false_no_link(self) -> None:
        """returns false when no shared link exists."""
        session = _mock_session()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute.return_value = mock_result

        assert (
            await check_shared_access(session, _ASSET_ID, _TARGET_CASE) is False
        )
