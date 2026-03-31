"""rbac bypass scenario tests."""

from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest

from loom.services.case import (
    check_case_access,
    update_case,
)

_USER_ID = UUID("01912345-6789-7abc-8def-0123456789ab")
_CASE_ID = "01912345-6789-7abc-8def-0123456789cd"
_OTHER_USER = UUID("01912345-6789-7abc-8def-aaaaaaaaaaaa")


def _mock_session() -> AsyncMock:
    s = AsyncMock()
    s.add = MagicMock()
    s.commit = AsyncMock()
    s.flush = AsyncMock()
    s.refresh = AsyncMock()
    s.begin_nested = MagicMock(
        return_value=AsyncMock(
            __aenter__=AsyncMock(),
            __aexit__=AsyncMock(return_value=False),
        )
    )
    return s


class TestAccessDenied:
    """users without membership cannot access cases."""

    @pytest.mark.asyncio
    async def test_non_member_denied(self) -> None:
        """user not in case membership returns false."""
        session = _mock_session()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=mock_result)

        has_access = await check_case_access(session, _CASE_ID, str(_USER_ID))
        assert has_access is False

    @pytest.mark.asyncio
    async def test_member_granted(self) -> None:
        """user with membership returns true."""
        session = _mock_session()
        mock_membership = MagicMock()
        mock_membership.role = "viewer"
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_membership
        session.execute = AsyncMock(return_value=mock_result)

        has_access = await check_case_access(session, _CASE_ID, str(_USER_ID))
        assert has_access is True


class TestFieldWhitelistEnforcement:
    """update operations reject non-whitelisted fields."""

    @pytest.mark.asyncio
    async def test_cannot_overwrite_id_via_update(
        self,
    ) -> None:
        """id field must not be updatable."""
        session = _mock_session()
        mock_case = MagicMock()
        mock_case.id = UUID(_CASE_ID)
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = mock_case
        session.execute = AsyncMock(return_value=mock_result)

        with pytest.raises(ValueError, match="not updatable"):
            await update_case(session, _CASE_ID, {"id": "evil-id"})

    @pytest.mark.asyncio
    async def test_cannot_overwrite_created_by(self) -> None:
        """created_by field must not be updatable."""
        session = _mock_session()
        mock_case = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = mock_case
        session.execute = AsyncMock(return_value=mock_result)

        with pytest.raises(ValueError, match="not updatable"):
            await update_case(
                session,
                _CASE_ID,
                {"created_by": str(_OTHER_USER)},
            )
