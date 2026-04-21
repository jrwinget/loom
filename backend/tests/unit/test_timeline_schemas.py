"""unit tests for timeline schema validation."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from loom.schemas.timeline import (
    EVIDENCE_RELATIONSHIPS,
    TIME_PRECISIONS,
    EvidenceLinkCreate,
    TimelineEventCreate,
)

_NOW = datetime(2025, 6, 1, tzinfo=UTC)


def test_event_create_valid() -> None:
    """valid event create passes validation."""
    event = TimelineEventCreate(
        title="Protest at city hall",
        event_time_start=_NOW,
        time_precision="exact",
    )
    assert event.title == "Protest at city hall"
    assert event.time_precision == "exact"
    assert event.status == "draft"


def test_event_create_all_time_precisions() -> None:
    """all valid time_precision values are accepted."""
    for precision in TIME_PRECISIONS:
        event = TimelineEventCreate(
            title="Test",
            event_time_start=_NOW,
            time_precision=precision,
        )
        assert event.time_precision == precision


def test_event_create_invalid_time_precision() -> None:
    """invalid time_precision raises validation error."""
    with pytest.raises(ValidationError, match="time_precision"):
        TimelineEventCreate(
            title="Test",
            event_time_start=_NOW,
            time_precision="wrong",
        )


def test_event_create_invalid_status() -> None:
    """invalid status raises validation error."""
    with pytest.raises(ValidationError, match="status"):
        TimelineEventCreate(
            title="Test",
            event_time_start=_NOW,
            status="invalid",
        )


def test_event_create_missing_title() -> None:
    """missing title raises validation error."""
    with pytest.raises(ValidationError):
        TimelineEventCreate(
            event_time_start=_NOW,  # type: ignore[call-arg]
        )


def test_event_create_empty_title() -> None:
    """empty title raises validation error."""
    with pytest.raises(ValidationError):
        TimelineEventCreate(
            title="",
            event_time_start=_NOW,
        )


def test_event_create_missing_time_start() -> None:
    """missing event_time_start raises validation error."""
    with pytest.raises(ValidationError):
        TimelineEventCreate(
            title="Test",  # type: ignore[call-arg]
        )


def test_evidence_link_valid_relationships() -> None:
    """all valid relationship values are accepted."""
    for rel in EVIDENCE_RELATIONSHIPS:
        link = EvidenceLinkCreate(relationship=rel)
        assert link.relationship == rel


def test_evidence_link_invalid_relationship() -> None:
    """invalid relationship raises validation error."""
    with pytest.raises(ValidationError, match="relationship"):
        EvidenceLinkCreate(relationship="invalid")


def test_evidence_link_missing_relationship() -> None:
    """missing relationship raises validation error."""
    with pytest.raises(ValidationError):
        EvidenceLinkCreate()  # type: ignore[call-arg]


def test_event_update_invalid_status() -> None:
    """update with invalid status raises validation error."""
    from loom.schemas.timeline import TimelineEventUpdate

    with pytest.raises(ValidationError, match="status"):
        TimelineEventUpdate(status="invalid")


def test_event_update_invalid_time_precision() -> None:
    """update with invalid time_precision raises error."""
    from loom.schemas.timeline import TimelineEventUpdate

    with pytest.raises(ValidationError, match="time_precision"):
        TimelineEventUpdate(time_precision="wrong")


def test_event_update_invalid_location_confidence() -> None:
    """update with invalid location_confidence raises error."""
    from loom.schemas.timeline import TimelineEventUpdate

    with pytest.raises(ValidationError, match="location_confidence"):
        TimelineEventUpdate(location_confidence="bad")


def test_event_update_valid_fields() -> None:
    """update with valid optional fields passes."""
    from loom.schemas.timeline import TimelineEventUpdate

    update = TimelineEventUpdate(
        status="accepted",
        time_precision="exact",
        location_confidence="verified",
    )
    assert update.status == "accepted"
    assert update.time_precision == "exact"
    assert update.location_confidence == "verified"


def test_event_update_none_fields() -> None:
    """update with None fields is valid (no change)."""
    from loom.schemas.timeline import TimelineEventUpdate

    update = TimelineEventUpdate()
    assert update.status is None
    assert update.time_precision is None
    assert update.location_confidence is None


def test_event_create_invalid_location_confidence() -> None:
    """invalid location_confidence raises validation error."""
    with pytest.raises(ValidationError, match="location_confidence"):
        TimelineEventCreate(
            title="Test",
            event_time_start=_NOW,
            location_confidence="bad",
        )
