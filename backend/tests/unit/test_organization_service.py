"""unit tests for loom.services.organization."""

from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest

from loom.models.organization import Organization, OrganizationMembership
from loom.models.user import User
from loom.services.organization import (
    add_member,
    check_org_admin,
    create_org,
    get_org,
    list_members,
    list_orgs,
    remove_member,
    update_org,
)

_USER_ID = str(uuid4())
_ORG_ID = str(uuid4())


def _mock_session() -> AsyncMock:
    s = AsyncMock()
    s.add = MagicMock()
    s.commit = AsyncMock()
    s.flush = AsyncMock()
    s.refresh = AsyncMock()
    s.delete = AsyncMock()

    # mock begin_nested() as async context manager
    nested_cm = AsyncMock()
    nested_cm.__aenter__ = AsyncMock(return_value=None)
    nested_cm.__aexit__ = AsyncMock(return_value=False)
    s.begin_nested = MagicMock(return_value=nested_cm)

    return s


# ── create_org ──────────────────────────────────────────────


class TestCreateOrg:
    @pytest.mark.asyncio
    async def test_creates_org_and_admin_membership(self) -> None:
        """should add org, flush, add admin membership, commit."""
        session = _mock_session()
        result = await create_org(
            session, "NLG Portland", "Portland chapter", _USER_ID
        )
        assert isinstance(result, Organization)
        assert result.name == "NLG Portland"
        assert result.description == "Portland chapter"
        assert session.add.call_count == 2
        assert session.flush.await_count == 1
        assert session.commit.await_count == 1

    @pytest.mark.asyncio
    async def test_membership_role_is_admin(self) -> None:
        """creator gets admin role on the org."""
        session = _mock_session()
        await create_org(session, "Org", None, _USER_ID)
        membership = session.add.call_args_list[1][0][0]
        assert isinstance(membership, OrganizationMembership)
        assert membership.role == "admin"
        assert membership.user_id == UUID(_USER_ID)

    @pytest.mark.asyncio
    async def test_description_none(self) -> None:
        """description can be none."""
        session = _mock_session()
        result = await create_org(session, "Org", None, _USER_ID)
        assert result.description is None


# ── get_org ─────────────────────────────────────────────────


class TestGetOrg:
    @pytest.mark.asyncio
    async def test_returns_org(self) -> None:
        session = _mock_session()
        org = Organization(name="O")
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = org
        session.execute.return_value = mock_result

        assert await get_org(session, _ORG_ID) is org

    @pytest.mark.asyncio
    async def test_returns_none(self) -> None:
        session = _mock_session()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute.return_value = mock_result

        assert await get_org(session, _ORG_ID) is None


# ── update_org ──────────────────────────────────────────────


class TestUpdateOrg:
    @pytest.mark.asyncio
    async def test_partial_update(self) -> None:
        """updates only non-none fields."""
        session = _mock_session()
        org = Organization(name="Old", description="keep")
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = org
        session.execute.return_value = mock_result

        updated = await update_org(
            session, _ORG_ID, {"name": "New", "description": None}
        )
        assert updated.name == "New"
        assert updated.description == "keep"
        session.commit.assert_awaited_once()
        session.refresh.assert_awaited_once_with(org)


# ── list_orgs ───────────────────────────────────────────────


class TestListOrgs:
    @pytest.mark.asyncio
    async def test_admin_sees_all(self) -> None:
        """admin role returns all orgs."""
        session = _mock_session()
        org = Organization(name="O")
        count_result = MagicMock()
        count_result.scalar_one.return_value = 1
        row = MagicMock()
        row.__getitem__ = lambda self, i: [org, 5][i]
        data_result = MagicMock()
        data_result.all.return_value = [row]
        session.execute.side_effect = [count_result, data_result]

        orgs, total = await list_orgs(session, _USER_ID, "admin")
        assert total == 1
        assert len(orgs) == 1
        assert orgs[0].member_count == 5

    @pytest.mark.asyncio
    async def test_non_admin_filters(self) -> None:
        """analyst role filters to user memberships."""
        session = _mock_session()
        count_result = MagicMock()
        count_result.scalar_one.return_value = 0
        data_result = MagicMock()
        data_result.all.return_value = []
        session.execute.side_effect = [count_result, data_result]

        orgs, total = await list_orgs(session, _USER_ID, "analyst")
        assert total == 0
        assert orgs == []

    @pytest.mark.asyncio
    async def test_null_member_count(self) -> None:
        """null member_count defaults to 0."""
        session = _mock_session()
        org = Organization(name="O")
        count_result = MagicMock()
        count_result.scalar_one.return_value = 1
        row = MagicMock()
        row.__getitem__ = lambda self, i: [org, None][i]
        data_result = MagicMock()
        data_result.all.return_value = [row]
        session.execute.side_effect = [count_result, data_result]

        orgs, _ = await list_orgs(session, _USER_ID, "admin")
        assert orgs[0].member_count == 0


# ── add_member ──────────────────────────────────────────────


class TestAddMember:
    @pytest.mark.asyncio
    async def test_adds_member(self) -> None:
        session = _mock_session()
        result = await add_member(session, _ORG_ID, _USER_ID, "member")
        assert isinstance(result, OrganizationMembership)
        assert result.org_id == UUID(_ORG_ID)
        assert result.user_id == UUID(_USER_ID)
        assert result.role == "member"
        session.add.assert_called_once()
        session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_default_role_is_member(self) -> None:
        """role defaults to member."""
        session = _mock_session()
        result = await add_member(session, _ORG_ID, _USER_ID)
        assert result.role == "member"


# ── remove_member ───────────────────────────────────────────


class TestRemoveMember:
    @pytest.mark.asyncio
    async def test_removes_existing(self) -> None:
        session = _mock_session()
        membership = OrganizationMembership(
            org_id=UUID(_ORG_ID),
            user_id=UUID(_USER_ID),
            role="member",
        )
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = membership
        session.execute.return_value = mock_result

        assert await remove_member(session, _ORG_ID, _USER_ID) is True
        session.delete.assert_awaited_once_with(membership)

    @pytest.mark.asyncio
    async def test_returns_false_when_not_found(self) -> None:
        session = _mock_session()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute.return_value = mock_result

        assert await remove_member(session, _ORG_ID, _USER_ID) is False
        session.delete.assert_not_awaited()


# ── list_members ────────────────────────────────────────────


class TestListMembers:
    @pytest.mark.asyncio
    async def test_returns_members_with_email(self) -> None:
        session = _mock_session()
        membership = OrganizationMembership(
            org_id=UUID(_ORG_ID),
            user_id=UUID(_USER_ID),
            role="admin",
        )
        row = MagicMock()
        row.__getitem__ = lambda self, i: [membership, "admin@nlg.org"][i]
        mock_result = MagicMock()
        mock_result.all.return_value = [row]
        session.execute.return_value = mock_result

        members = await list_members(session, _ORG_ID)
        assert len(members) == 1
        assert members[0].user_email == "admin@nlg.org"

    @pytest.mark.asyncio
    async def test_empty_org(self) -> None:
        session = _mock_session()
        mock_result = MagicMock()
        mock_result.all.return_value = []
        session.execute.return_value = mock_result

        assert await list_members(session, _ORG_ID) == []


# ── check_org_admin ─────────────────────────────────────────


class TestCheckOrgAdmin:
    @pytest.mark.asyncio
    async def test_system_admin_bypasses(self) -> None:
        """system admin returns true without checking membership."""
        session = _mock_session()
        user = User(
            email="a@t.com",
            display_name="A",
            role="admin",
            password_hash="x",
        )
        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user
        session.execute.return_value = user_result

        assert await check_org_admin(session, _ORG_ID, _USER_ID) is True
        assert session.execute.await_count == 1

    @pytest.mark.asyncio
    async def test_org_admin_returns_true(self) -> None:
        """org admin membership returns true."""
        session = _mock_session()
        user = User(
            email="u@t.com",
            display_name="U",
            role="analyst",
            password_hash="x",
        )
        membership = OrganizationMembership(
            org_id=UUID(_ORG_ID),
            user_id=UUID(_USER_ID),
            role="admin",
        )
        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user
        mem_result = MagicMock()
        mem_result.scalar_one_or_none.return_value = membership
        session.execute.side_effect = [user_result, mem_result]

        assert await check_org_admin(session, _ORG_ID, _USER_ID) is True

    @pytest.mark.asyncio
    async def test_org_member_not_admin(self) -> None:
        """regular member returns false."""
        session = _mock_session()
        user = User(
            email="u@t.com",
            display_name="U",
            role="analyst",
            password_hash="x",
        )
        membership = OrganizationMembership(
            org_id=UUID(_ORG_ID),
            user_id=UUID(_USER_ID),
            role="member",
        )
        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user
        mem_result = MagicMock()
        mem_result.scalar_one_or_none.return_value = membership
        session.execute.side_effect = [user_result, mem_result]

        assert await check_org_admin(session, _ORG_ID, _USER_ID) is False

    @pytest.mark.asyncio
    async def test_no_membership_returns_false(self) -> None:
        """no membership returns false."""
        session = _mock_session()
        user = User(
            email="u@t.com",
            display_name="U",
            role="analyst",
            password_hash="x",
        )
        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user
        mem_result = MagicMock()
        mem_result.scalar_one_or_none.return_value = None
        session.execute.side_effect = [user_result, mem_result]

        assert await check_org_admin(session, _ORG_ID, _USER_ID) is False

    @pytest.mark.asyncio
    async def test_unknown_user_returns_false(self) -> None:
        """nonexistent user returns false."""
        session = _mock_session()
        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = None
        mem_result = MagicMock()
        mem_result.scalar_one_or_none.return_value = None
        session.execute.side_effect = [user_result, mem_result]

        assert await check_org_admin(session, _ORG_ID, _USER_ID) is False
