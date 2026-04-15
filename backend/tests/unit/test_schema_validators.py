"""Tests for schema field validators."""

import pytest
from pydantic import ValidationError

from loom.schemas.case import CaseMemberCreate
from loom.schemas.organization import SharedEvidenceCreate


class TestCaseMemberRoleValidation:
    """CaseMemberCreate.role field_validator."""

    @pytest.mark.parametrize("role", ["viewer", "editor", "owner"])
    def test_valid_roles_accepted(self, role: str) -> None:
        member = CaseMemberCreate(user_id="abc", role=role)
        assert member.role == role

    def test_default_role_is_viewer(self) -> None:
        member = CaseMemberCreate(user_id="abc")
        assert member.role == "viewer"

    @pytest.mark.parametrize("role", ["admin", "superuser", ""])
    def test_invalid_role_rejected(self, role: str) -> None:
        with pytest.raises(ValidationError, match="role must be"):
            CaseMemberCreate(user_id="abc", role=role)


class TestSharedEvidenceAccessLevelValidation:
    """SharedEvidenceCreate.access_level field_validator."""

    @pytest.mark.parametrize(
        "level",
        ["view", "annotate"],
    )
    def test_valid_access_levels_accepted(
        self,
        level: str,
    ) -> None:
        ev = SharedEvidenceCreate(
            target_case_id="t",
            asset_id="a",
            access_level=level,
        )
        assert ev.access_level == level

    def test_default_access_level_is_view(self) -> None:
        ev = SharedEvidenceCreate(
            target_case_id="t",
            asset_id="a",
        )
        assert ev.access_level == "view"

    @pytest.mark.parametrize(
        "level",
        ["edit", "admin", ""],
    )
    def test_invalid_access_level_rejected(
        self,
        level: str,
    ) -> None:
        with pytest.raises(ValidationError, match="access_level must be"):
            SharedEvidenceCreate(
                target_case_id="t",
                asset_id="a",
                access_level=level,
            )
