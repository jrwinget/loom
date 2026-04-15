"""unit tests for loom.services.case."""

from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest

from loom.models.case import Case, CaseMembership
from loom.models.user import User
from loom.services.case import (
    _ROLE_HIERARCHY,
    _UPDATABLE_CASE_FIELDS,
    add_member,
    check_case_access,
    create_case,
    get_case,
    list_cases,
    list_members,
    remove_member,
    update_case,
)

_USER_ID = str(uuid4())
_CASE_ID = str(uuid4())


def _mock_session() -> AsyncMock:
    """build a mock async session with standard helpers."""
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


# ── create_case ─────────────────────────────────────────────


class TestCreateCase:
    @pytest.mark.asyncio
    async def test_creates_case_and_membership(self) -> None:
        """should add case, flush, add membership, commit."""
        session = _mock_session()
        result = await create_case(session, "Test Case", "desc", _USER_ID)
        # two session.add calls: case + membership
        assert session.add.call_count == 2
        assert session.flush.await_count == 1
        assert session.commit.await_count == 1
        assert session.refresh.await_count == 1
        assert isinstance(result, Case)
        assert result.name == "Test Case"
        assert result.description == "desc"
        assert result.created_by == _USER_ID

    @pytest.mark.asyncio
    async def test_membership_role_is_owner(self) -> None:
        """creator gets owner role on the case."""
        session = _mock_session()
        await create_case(session, "C", None, _USER_ID)
        # second add call is the membership
        membership = session.add.call_args_list[1][0][0]
        assert isinstance(membership, CaseMembership)
        assert membership.role == "owner"
        assert membership.granted_by == _USER_ID

    @pytest.mark.asyncio
    async def test_description_none(self) -> None:
        """description can be none."""
        session = _mock_session()
        result = await create_case(session, "No Desc", None, _USER_ID)
        assert result.description is None


# ── get_case ────────────────────────────────────────────────


class TestGetCase:
    @pytest.mark.asyncio
    async def test_returns_case_when_found(self) -> None:
        """returns the case object from the query."""
        session = _mock_session()
        case = Case(name="Found", created_by=_USER_ID)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = case
        session.execute.return_value = mock_result

        got = await get_case(session, _CASE_ID)
        assert got is case

    @pytest.mark.asyncio
    async def test_returns_none_when_missing(self) -> None:
        """returns none if case does not exist."""
        session = _mock_session()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute.return_value = mock_result

        got = await get_case(session, _CASE_ID)
        assert got is None


# ── update_case ─────────────────────────────────────────────


class TestUpdateCase:
    @pytest.mark.asyncio
    async def test_partial_update_sets_attributes(self) -> None:
        """updates only provided non-none fields."""
        session = _mock_session()
        case = Case(name="Old", description="old", created_by=_USER_ID)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = case
        session.execute.return_value = mock_result

        updated = await update_case(
            session, _CASE_ID, {"name": "New", "description": None}
        )
        # name changed, description stays (none values skipped)
        assert updated.name == "New"
        assert updated.description == "old"
        assert session.commit.await_count == 1

    @pytest.mark.asyncio
    async def test_update_commits_and_refreshes(self) -> None:
        """should commit and refresh after update."""
        session = _mock_session()
        case = Case(name="X", created_by=_USER_ID)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = case
        session.execute.return_value = mock_result

        await update_case(session, _CASE_ID, {"name": "Y"})
        session.commit.assert_awaited_once()
        session.refresh.assert_awaited_once_with(case)


# ── update_case field whitelist ────────────────────────────


class TestUpdateCaseFieldWhitelist:
    @pytest.mark.asyncio
    async def test_rejects_non_updatable_field(self) -> None:
        """setattr rejects fields not in whitelist."""
        session = _mock_session()
        case = Case(name="X", created_by=_USER_ID)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = case
        session.execute.return_value = mock_result

        with pytest.raises(ValueError, match="not updatable"):
            await update_case(session, _CASE_ID, {"id": "evil"})

    @pytest.mark.asyncio
    async def test_rejects_created_by(self) -> None:
        """cannot overwrite created_by via update."""
        session = _mock_session()
        case = Case(name="X", created_by=_USER_ID)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = case
        session.execute.return_value = mock_result

        with pytest.raises(ValueError, match="not updatable"):
            await update_case(session, _CASE_ID, {"created_by": "evil"})

    @pytest.mark.asyncio
    async def test_allows_name_update(self) -> None:
        """name is in the whitelist and should be accepted."""
        session = _mock_session()
        case = Case(name="Old", created_by=_USER_ID)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = case
        session.execute.return_value = mock_result

        updated = await update_case(session, _CASE_ID, {"name": "New"})
        assert updated.name == "New"

    @pytest.mark.asyncio
    async def test_allows_all_whitelisted_fields(self) -> None:
        """all fields in the whitelist are accepted."""
        session = _mock_session()
        case = Case(name="X", created_by=_USER_ID)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = case
        session.execute.return_value = mock_result

        data = {f: "val" for f in _UPDATABLE_CASE_FIELDS}
        # should not raise
        await update_case(session, _CASE_ID, data)

    @pytest.mark.asyncio
    async def test_whitelist_is_frozen(self) -> None:
        """whitelist must be a frozenset to prevent mutation."""
        assert isinstance(_UPDATABLE_CASE_FIELDS, frozenset)


# ── list_cases ──────────────────────────────────────────────


class TestListCases:
    @pytest.mark.asyncio
    async def test_admin_sees_all_cases(self) -> None:
        """admin role should not filter by membership."""
        session = _mock_session()
        case = Case(name="C1", created_by=_USER_ID)
        # first execute: count query
        count_result = MagicMock()
        count_result.scalar_one.return_value = 1
        # second execute: paginated query
        row = MagicMock()
        row.__getitem__ = lambda self, i: [case, 3, 5][i]
        data_result = MagicMock()
        data_result.all.return_value = [row]
        session.execute.side_effect = [count_result, data_result]

        cases, total = await list_cases(session, _USER_ID, "admin", 0, 20)
        assert total == 1
        assert len(cases) == 1
        assert cases[0].asset_count == 3
        assert cases[0].event_count == 5

    @pytest.mark.asyncio
    async def test_non_admin_filters_by_membership(self) -> None:
        """analyst role should join on membership table."""
        session = _mock_session()
        count_result = MagicMock()
        count_result.scalar_one.return_value = 0
        data_result = MagicMock()
        data_result.all.return_value = []
        session.execute.side_effect = [count_result, data_result]

        cases, total = await list_cases(session, _USER_ID, "analyst", 0, 20)
        assert total == 0
        assert cases == []

    @pytest.mark.asyncio
    async def test_counts_default_to_zero(self) -> None:
        """null counts from db should become 0."""
        session = _mock_session()
        case = Case(name="C2", created_by=_USER_ID)
        count_result = MagicMock()
        count_result.scalar_one.return_value = 1
        row = MagicMock()
        row.__getitem__ = lambda self, i: [case, None, None][i]
        data_result = MagicMock()
        data_result.all.return_value = [row]
        session.execute.side_effect = [count_result, data_result]

        cases, _ = await list_cases(session, _USER_ID, "admin", 0, 20)
        assert cases[0].asset_count == 0
        assert cases[0].event_count == 0


# ── check_case_access ──────────────────────────────────────


class TestCheckCaseAccess:
    @pytest.mark.asyncio
    async def test_admin_always_has_access(self) -> None:
        """system admin bypasses membership check."""
        session = _mock_session()
        user = User(
            email="admin@test.com",
            display_name="Admin",
            role="admin",
            password_hash="x",
        )
        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user
        session.execute.return_value = user_result

        assert (
            await check_case_access(session, _CASE_ID, _USER_ID, "owner")
            is True
        )
        # only one execute call (user lookup), no membership
        assert session.execute.await_count == 1

    @pytest.mark.asyncio
    async def test_owner_has_editor_access(self) -> None:
        """owner role satisfies editor requirement."""
        session = _mock_session()
        user = User(
            email="u@t.com",
            display_name="U",
            role="analyst",
            password_hash="x",
        )
        membership = CaseMembership(
            case_id=UUID(_CASE_ID),
            user_id=UUID(_USER_ID),
            role="owner",
            granted_by=UUID(_USER_ID),
        )
        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user
        mem_result = MagicMock()
        mem_result.scalar_one_or_none.return_value = membership
        session.execute.side_effect = [user_result, mem_result]

        assert (
            await check_case_access(session, _CASE_ID, _USER_ID, "editor")
            is True
        )

    @pytest.mark.asyncio
    async def test_viewer_cannot_edit(self) -> None:
        """viewer role does not satisfy editor requirement."""
        session = _mock_session()
        user = User(
            email="u@t.com",
            display_name="U",
            role="analyst",
            password_hash="x",
        )
        membership = CaseMembership(
            case_id=UUID(_CASE_ID),
            user_id=UUID(_USER_ID),
            role="viewer",
            granted_by=UUID(_USER_ID),
        )
        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user
        mem_result = MagicMock()
        mem_result.scalar_one_or_none.return_value = membership
        session.execute.side_effect = [user_result, mem_result]

        assert (
            await check_case_access(session, _CASE_ID, _USER_ID, "editor")
            is False
        )

    @pytest.mark.asyncio
    async def test_no_membership_returns_false(self) -> None:
        """no membership means no access."""
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

        assert (
            await check_case_access(session, _CASE_ID, _USER_ID, "viewer")
            is False
        )

    @pytest.mark.asyncio
    async def test_unknown_user_returns_false(self) -> None:
        """nonexistent user returns false."""
        session = _mock_session()
        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = None
        mem_result = MagicMock()
        mem_result.scalar_one_or_none.return_value = None
        session.execute.side_effect = [user_result, mem_result]

        assert (
            await check_case_access(session, _CASE_ID, _USER_ID, "viewer")
            is False
        )

    def test_role_hierarchy_ordering(self) -> None:
        """hierarchy levels are viewer < editor < owner."""
        assert _ROLE_HIERARCHY["viewer"] < _ROLE_HIERARCHY["editor"]
        assert _ROLE_HIERARCHY["editor"] < _ROLE_HIERARCHY["owner"]

    @pytest.mark.asyncio
    async def test_editor_has_viewer_access(self) -> None:
        """editor role satisfies viewer requirement."""
        session = _mock_session()
        user = User(
            email="u@t.com",
            display_name="U",
            role="analyst",
            password_hash="x",
        )
        membership = CaseMembership(
            case_id=UUID(_CASE_ID),
            user_id=UUID(_USER_ID),
            role="editor",
            granted_by=UUID(_USER_ID),
        )
        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user
        mem_result = MagicMock()
        mem_result.scalar_one_or_none.return_value = membership
        session.execute.side_effect = [user_result, mem_result]

        assert (
            await check_case_access(session, _CASE_ID, _USER_ID, "viewer")
            is True
        )


# ── add_member ──────────────────────────────────────────────


class TestAddMember:
    @pytest.mark.asyncio
    async def test_adds_membership(self) -> None:
        """creates membership with correct fields."""
        session = _mock_session()
        granted_by = str(uuid4())
        result = await add_member(
            session, _CASE_ID, _USER_ID, "editor", granted_by
        )
        assert isinstance(result, CaseMembership)
        assert result.role == "editor"
        assert result.case_id == UUID(_CASE_ID)
        assert result.user_id == UUID(_USER_ID)
        assert result.granted_by == UUID(granted_by)
        session.add.assert_called_once()
        session.commit.assert_awaited_once()
        session.refresh.assert_awaited_once()


# ── remove_member ───────────────────────────────────────────


class TestRemoveMember:
    @pytest.mark.asyncio
    async def test_removes_existing_membership(self) -> None:
        """returns true and deletes when membership found."""
        session = _mock_session()
        membership = CaseMembership(
            case_id=UUID(_CASE_ID),
            user_id=UUID(_USER_ID),
            role="editor",
            granted_by=UUID(_USER_ID),
        )
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = membership
        session.execute.return_value = mock_result

        assert await remove_member(session, _CASE_ID, _USER_ID) is True
        session.delete.assert_awaited_once_with(membership)
        session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_returns_false_when_not_found(self) -> None:
        """returns false when membership does not exist."""
        session = _mock_session()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute.return_value = mock_result

        assert await remove_member(session, _CASE_ID, _USER_ID) is False
        session.delete.assert_not_awaited()


# ── list_members ────────────────────────────────────────────


class TestListMembers:
    @pytest.mark.asyncio
    async def test_returns_members_with_email(self) -> None:
        """attaches user_email from joined user row."""
        session = _mock_session()
        membership = CaseMembership(
            case_id=UUID(_CASE_ID),
            user_id=UUID(_USER_ID),
            role="viewer",
            granted_by=UUID(_USER_ID),
        )
        row = MagicMock()
        row.__getitem__ = lambda self, i: [membership, "user@test.com"][i]
        mock_result = MagicMock()
        mock_result.all.return_value = [row]
        session.execute.return_value = mock_result

        members = await list_members(session, _CASE_ID)
        assert len(members) == 1
        assert members[0].user_email == "user@test.com"

    @pytest.mark.asyncio
    async def test_returns_empty_list(self) -> None:
        """returns empty list when no members."""
        session = _mock_session()
        mock_result = MagicMock()
        mock_result.all.return_value = []
        session.execute.return_value = mock_result

        members = await list_members(session, _CASE_ID)
        assert members == []
