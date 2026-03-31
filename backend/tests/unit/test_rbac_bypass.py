"""rbac bypass scenario tests."""

from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest

from loom.models.case import CaseMembership
from loom.models.user import User
from loom.services.case import (
    _ROLE_HIERARCHY,
    check_case_access,
)

_CASE_A_ID = str(uuid4())
_CASE_B_ID = str(uuid4())
_USER_ID = str(uuid4())
_OWNER_ID = str(uuid4())


def _mock_session() -> AsyncMock:
    """build a mock async session with standard helpers."""
    s = AsyncMock()
    s.add = MagicMock()
    s.commit = AsyncMock()
    s.flush = AsyncMock()
    s.refresh = AsyncMock()
    s.delete = AsyncMock()

    nested_cm = AsyncMock()
    nested_cm.__aenter__ = AsyncMock(return_value=None)
    nested_cm.__aexit__ = AsyncMock(return_value=False)
    s.begin_nested = MagicMock(return_value=nested_cm)

    return s


def _user(
    role: str = "analyst",
    user_id: str | None = None,
) -> User:
    """build a mock user with the given system role."""
    u = User(
        email="u@test.com",
        display_name="User",
        role=role,
        password_hash="x",
    )
    if user_id:
        u.id = UUID(user_id)
    return u


def _membership(
    case_id: str,
    user_id: str,
    role: str,
) -> CaseMembership:
    """build a mock case membership."""
    return CaseMembership(
        case_id=UUID(case_id),
        user_id=UUID(user_id),
        role=role,
        granted_by=UUID(user_id),
    )


# ── privilege escalation ──────────────────────────────────


class TestPrivilegeEscalation:
    """users cannot escalate their own privileges."""

    @pytest.mark.asyncio
    async def test_viewer_cannot_satisfy_editor(self) -> None:
        """viewer role must not satisfy editor requirement."""
        session = _mock_session()
        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = _user("analyst")
        mem_result = MagicMock()
        mem_result.scalar_one_or_none.return_value = _membership(
            _CASE_A_ID, _USER_ID, "viewer"
        )
        session.execute.side_effect = [user_result, mem_result]

        result = await check_case_access(
            session, _CASE_A_ID, _USER_ID, "editor"
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_viewer_cannot_satisfy_owner(self) -> None:
        """viewer role must not satisfy owner requirement."""
        session = _mock_session()
        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = _user("analyst")
        mem_result = MagicMock()
        mem_result.scalar_one_or_none.return_value = _membership(
            _CASE_A_ID, _USER_ID, "viewer"
        )
        session.execute.side_effect = [user_result, mem_result]

        result = await check_case_access(session, _CASE_A_ID, _USER_ID, "owner")
        assert result is False

    @pytest.mark.asyncio
    async def test_editor_cannot_satisfy_owner(self) -> None:
        """editor role must not satisfy owner requirement."""
        session = _mock_session()
        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = _user("analyst")
        mem_result = MagicMock()
        mem_result.scalar_one_or_none.return_value = _membership(
            _CASE_A_ID, _USER_ID, "editor"
        )
        session.execute.side_effect = [user_result, mem_result]

        result = await check_case_access(session, _CASE_A_ID, _USER_ID, "owner")
        assert result is False

    @pytest.mark.asyncio
    async def test_non_member_cannot_access_case(
        self,
    ) -> None:
        """user not in case membership cannot access."""
        session = _mock_session()
        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = _user("analyst")
        mem_result = MagicMock()
        mem_result.scalar_one_or_none.return_value = None
        session.execute.side_effect = [user_result, mem_result]

        result = await check_case_access(
            session, _CASE_A_ID, _USER_ID, "viewer"
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_unknown_role_defaults_to_zero(self) -> None:
        """unknown roles in hierarchy default to level 0."""
        assert _ROLE_HIERARCHY.get("nonexistent", 0) == 0

    def test_role_hierarchy_is_strictly_ordered(self) -> None:
        """each level is strictly greater than the previous."""
        assert (
            _ROLE_HIERARCHY["viewer"]
            < _ROLE_HIERARCHY["editor"]
            < _ROLE_HIERARCHY["owner"]
        )


# ── cross-resource access ─────────────────────────────────


class TestCrossResourceAccess:
    """users cannot access resources across cases."""

    @pytest.mark.asyncio
    async def test_membership_on_case_a_not_valid_for_b(
        self,
    ) -> None:
        """membership on case A does not grant access to
        case B."""
        session = _mock_session()
        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = _user("analyst")
        # querying case B returns no membership
        mem_result = MagicMock()
        mem_result.scalar_one_or_none.return_value = None
        session.execute.side_effect = [user_result, mem_result]

        result = await check_case_access(
            session, _CASE_B_ID, _USER_ID, "viewer"
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_admin_bypasses_membership_check(
        self,
    ) -> None:
        """admin system role bypasses case membership;
        verify only one query."""
        session = _mock_session()
        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = _user("admin")
        session.execute.return_value = user_result

        result = await check_case_access(session, _CASE_A_ID, _USER_ID, "owner")
        assert result is True
        # admin path only executes the user lookup
        assert session.execute.await_count == 1
