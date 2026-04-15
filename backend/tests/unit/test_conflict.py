import pytest
from pydantic import ValidationError

from loom.schemas.conflict import (
    ConflictResolutionCreate,
    ConflictResolutionUpdate,
)

# valid resolution types
_VALID_TYPES = (
    "accepted_supporting",
    "accepted_contradicting",
    "noted",
    "dismissed",
)


class TestResolutionTypeValidation:
    """resolution_type field validation."""

    @pytest.mark.parametrize("rtype", _VALID_TYPES)
    def test_valid_resolution_types(self, rtype: str) -> None:
        """all four resolution types are accepted."""
        schema = ConflictResolutionCreate(resolution_type=rtype)
        assert schema.resolution_type == rtype

    def test_invalid_resolution_type_rejected(self) -> None:
        """unknown resolution type raises validation error."""
        with pytest.raises(ValidationError):
            ConflictResolutionCreate(resolution_type="invalid")

    def test_create_with_notes(self) -> None:
        """notes field is optional on create."""
        schema = ConflictResolutionCreate(
            resolution_type="noted",
            notes="analyst reviewed",
        )
        assert schema.notes == "analyst reviewed"

    def test_create_notes_default_none(self) -> None:
        """notes defaults to none."""
        schema = ConflictResolutionCreate(resolution_type="dismissed")
        assert schema.notes is None

    def test_update_all_none(self) -> None:
        """update with no fields is valid."""
        schema = ConflictResolutionUpdate()
        assert schema.resolution_type is None
        assert schema.notes is None

    def test_update_invalid_type_rejected(self) -> None:
        """update with invalid type raises validation error."""
        with pytest.raises(ValidationError):
            ConflictResolutionUpdate(resolution_type="bogus")

    def test_update_valid_type(self) -> None:
        """update with valid type passes."""
        schema = ConflictResolutionUpdate(resolution_type="dismissed")
        assert schema.resolution_type == "dismissed"


class TestConflictResolutionModel:
    """conflict resolution model instantiation."""

    def test_model_fields(self) -> None:
        """model has expected table name and columns."""
        from loom.models.conflict import ConflictResolution

        assert ConflictResolution.__tablename__ == "conflict_resolutions"

    def test_model_in_registry(self) -> None:
        """model is registered in models __init__."""
        from loom.models import ConflictResolution

        assert ConflictResolution is not None
