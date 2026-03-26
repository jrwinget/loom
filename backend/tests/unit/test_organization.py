from uuid import UUID

from loom.models.organization import (
    Organization,
    OrganizationMembership,
    SharedEvidenceLink,
)


def test_organization_model_fields() -> None:
    """organization model has expected fields."""
    org = Organization(
        name="NLG Chapter Portland",
        description="Portland chapter",
        is_active=True,
    )
    assert org.name == "NLG Chapter Portland"
    assert org.description == "Portland chapter"
    assert org.is_active is True


def test_organization_model_description_nullable() -> None:
    """organization description can be null."""
    org = Organization(name="Test Org")
    assert org.description is None


def test_organization_column_defaults() -> None:
    """organization table has correct column defaults."""
    cols = Organization.__table__.columns
    assert cols["is_active"].default.arg is True


def test_membership_model_with_role() -> None:
    """membership stores role correctly."""
    m = OrganizationMembership(
        org_id=UUID("01912345-6789-7abc-8def-0123456789ab"),
        user_id=UUID("01912345-6789-7abc-8def-0123456789cd"),
        role="admin",
    )
    assert m.role == "admin"
    assert m.org_id == UUID("01912345-6789-7abc-8def-0123456789ab")


def test_membership_column_defaults() -> None:
    """membership table defaults role to member."""
    cols = OrganizationMembership.__table__.columns
    assert cols["role"].default.arg == "member"


def test_membership_unique_constraint_defined() -> None:
    """unique constraint on (org_id, user_id) is declared."""
    constraints = OrganizationMembership.__table_args__
    assert len(constraints) == 1
    cols = [c.name for c in constraints[0].columns]
    assert "org_id" in cols
    assert "user_id" in cols


def test_shared_evidence_link_column_defaults() -> None:
    """shared evidence link table defaults access_level to view."""
    cols = SharedEvidenceLink.__table__.columns
    assert cols["access_level"].default.arg == "view"


def test_shared_evidence_link_expires_at_nullable() -> None:
    """shared evidence link expires_at can be null."""
    link = SharedEvidenceLink(
        source_case_id=UUID("01912345-6789-7abc-8def-0123456789ab"),
        target_case_id=UUID("01912345-6789-7abc-8def-0123456789cd"),
        asset_id=UUID("01912345-6789-7abc-8def-0123456789ef"),
        shared_by=UUID("01912345-6789-7abc-8def-012345678901"),
    )
    assert link.expires_at is None


def test_shared_evidence_link_with_access_level() -> None:
    """shared evidence link can set annotate access."""
    link = SharedEvidenceLink(
        source_case_id=UUID("01912345-6789-7abc-8def-0123456789ab"),
        target_case_id=UUID("01912345-6789-7abc-8def-0123456789cd"),
        asset_id=UUID("01912345-6789-7abc-8def-0123456789ef"),
        shared_by=UUID("01912345-6789-7abc-8def-012345678901"),
        access_level="annotate",
    )
    assert link.access_level == "annotate"
