"""unit tests for annotation schema validation."""

import pytest
from pydantic import ValidationError

from loom.schemas.annotation import (
    ANNOTATION_TYPES,
    AnnotationCreate,
)


def test_annotation_create_valid_types() -> None:
    """all valid annotation types are accepted."""
    for ann_type in ANNOTATION_TYPES:
        annotation = AnnotationCreate(
            type=ann_type,
            content="test content",
        )
        assert annotation.type == ann_type


def test_annotation_create_invalid_type() -> None:
    """invalid annotation type raises validation error."""
    with pytest.raises(ValidationError, match="type"):
        AnnotationCreate(
            type="invalid_type",
            content="test content",
        )


def test_annotation_create_missing_content() -> None:
    """missing content raises validation error."""
    with pytest.raises(ValidationError):
        AnnotationCreate(
            type="observation",  # type: ignore[call-arg]
        )


def test_annotation_create_empty_content() -> None:
    """empty content raises validation error."""
    with pytest.raises(ValidationError):
        AnnotationCreate(
            type="observation",
            content="",
        )


def test_annotation_create_optional_fields_default_none() -> None:
    """optional fields default to None."""
    annotation = AnnotationCreate(
        type="note",
        content="a note",
    )
    assert annotation.asset_id is None
    assert annotation.time_start is None
    assert annotation.time_end is None
    assert annotation.frame_number is None
    assert annotation.spatial_region is None


def test_annotation_create_with_all_fields() -> None:
    """annotation with all fields set validates correctly."""
    annotation = AnnotationCreate(
        type="claim",
        content="witness saw the event",
        asset_id="01912345-6789-7abc-8def-0123456789ab",
        time_start=10.5,
        time_end=20.0,
        frame_number=300,
        spatial_region={"x": 10, "y": 20, "w": 100, "h": 50},
    )
    assert annotation.type == "claim"
    assert annotation.time_start == 10.5
    assert annotation.spatial_region is not None


def test_annotation_update_valid_type() -> None:
    """update with valid type passes validation."""
    from loom.schemas.annotation import AnnotationUpdate

    update = AnnotationUpdate(type="dispute")
    assert update.type == "dispute"


def test_annotation_update_invalid_type() -> None:
    """update with invalid type raises validation error."""
    from loom.schemas.annotation import AnnotationUpdate

    with pytest.raises(ValidationError, match="type"):
        AnnotationUpdate(type="invalid_type")


def test_annotation_update_none_type() -> None:
    """update with None type is valid (no change)."""
    from loom.schemas.annotation import AnnotationUpdate

    update = AnnotationUpdate(type=None)
    assert update.type is None
