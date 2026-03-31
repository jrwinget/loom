"""unit tests for loom.services.annotation."""

from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest

from loom.models.annotation import Annotation
from loom.services.annotation import (
    _UPDATABLE_ANNOTATION_FIELDS,
    create_annotation,
    delete_annotation,
    get_annotation,
    list_annotations,
    update_annotation,
)

_CASE_ID = str(uuid4())
_USER_ID = str(uuid4())
_ANNO_ID = str(uuid4())
_ASSET_ID = str(uuid4())


def _mock_session() -> AsyncMock:
    s = AsyncMock()
    s.add = MagicMock()
    s.commit = AsyncMock()
    s.refresh = AsyncMock()
    s.delete = AsyncMock()
    return s


# ── create_annotation ──────────────────────────────────────


class TestCreateAnnotation:
    @pytest.mark.asyncio
    async def test_creates_with_all_fields(self) -> None:
        """stores all fields including optional ones."""
        session = _mock_session()
        data = {
            "type": "observation",
            "content": "Officer badge #1234 visible",
            "asset_id": _ASSET_ID,
            "time_start": 10.5,
            "time_end": 15.0,
            "frame_number": 300,
            "spatial_region": {"x": 100, "y": 200, "w": 50, "h": 50},
        }
        result = await create_annotation(session, _CASE_ID, data, _USER_ID)
        assert isinstance(result, Annotation)
        assert result.case_id == UUID(_CASE_ID)
        assert result.asset_id == UUID(_ASSET_ID)
        assert result.type == "observation"
        assert result.content == "Officer badge #1234 visible"
        assert result.time_start == 10.5
        assert result.time_end == 15.0
        assert result.frame_number == 300
        assert result.spatial_region == {
            "x": 100,
            "y": 200,
            "w": 50,
            "h": 50,
        }
        assert result.created_by == UUID(_USER_ID)
        session.add.assert_called_once()
        session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_asset_id_optional(self) -> None:
        """asset_id is none when not provided."""
        session = _mock_session()
        data = {"type": "note", "content": "general note"}
        result = await create_annotation(session, _CASE_ID, data, _USER_ID)
        assert result.asset_id is None

    @pytest.mark.asyncio
    async def test_temporal_fields_optional(self) -> None:
        """time_start, time_end, frame_number default none."""
        session = _mock_session()
        data = {"type": "claim", "content": "c"}
        result = await create_annotation(session, _CASE_ID, data, _USER_ID)
        assert result.time_start is None
        assert result.time_end is None
        assert result.frame_number is None
        assert result.spatial_region is None


# ── get_annotation ──────────────────────────────────────────


class TestGetAnnotation:
    @pytest.mark.asyncio
    async def test_returns_annotation_with_email(self) -> None:
        """attaches created_by_email from joined user row."""
        session = _mock_session()
        annotation = Annotation(
            case_id=UUID(_CASE_ID),
            type="observation",
            content="test",
            created_by=UUID(_USER_ID),
        )
        row = MagicMock()
        row.__getitem__ = lambda self, i: [annotation, "user@nlg.org"][i]
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = row
        session.execute.return_value = mock_result

        got = await get_annotation(session, _ANNO_ID)
        assert got is annotation
        assert got.created_by_email == "user@nlg.org"

    @pytest.mark.asyncio
    async def test_returns_none_when_missing(self) -> None:
        """returns none if annotation not found."""
        session = _mock_session()
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = None
        session.execute.return_value = mock_result

        assert await get_annotation(session, _ANNO_ID) is None


# ── list_annotations ────────────────────────────────────────


class TestListAnnotations:
    @pytest.mark.asyncio
    async def test_returns_paginated_annotations(self) -> None:
        """returns annotations and total count."""
        session = _mock_session()
        annotation = Annotation(
            case_id=UUID(_CASE_ID),
            type="observation",
            content="test",
            created_by=UUID(_USER_ID),
        )
        count_result = MagicMock()
        count_result.scalar_one.return_value = 1
        row = MagicMock()
        row.__getitem__ = lambda self, i: [annotation, "u@t.com"][i]
        data_result = MagicMock()
        data_result.all.return_value = [row]
        session.execute.side_effect = [count_result, data_result]

        annotations, total = await list_annotations(session, _CASE_ID)
        assert total == 1
        assert len(annotations) == 1
        assert annotations[0].created_by_email == "u@t.com"

    @pytest.mark.asyncio
    async def test_empty_result(self) -> None:
        """returns empty list when no annotations."""
        session = _mock_session()
        count_result = MagicMock()
        count_result.scalar_one.return_value = 0
        data_result = MagicMock()
        data_result.all.return_value = []
        session.execute.side_effect = [count_result, data_result]

        annotations, total = await list_annotations(session, _CASE_ID)
        assert total == 0
        assert annotations == []

    @pytest.mark.asyncio
    async def test_filters_accepted(self) -> None:
        """asset_id and annotation_type filters are accepted."""
        session = _mock_session()
        count_result = MagicMock()
        count_result.scalar_one.return_value = 0
        data_result = MagicMock()
        data_result.all.return_value = []
        session.execute.side_effect = [count_result, data_result]

        # should not raise
        await list_annotations(
            session,
            _CASE_ID,
            asset_id=_ASSET_ID,
            annotation_type="dispute",
        )


# ── update_annotation ──────────────────────────────────────


class TestUpdateAnnotation:
    @pytest.mark.asyncio
    async def test_partial_update(self) -> None:
        """updates only non-none fields."""
        session = _mock_session()
        annotation = Annotation(
            case_id=UUID(_CASE_ID),
            type="observation",
            content="old content",
            created_by=UUID(_USER_ID),
        )
        # first execute: select annotation
        scalar_result = MagicMock()
        scalar_result.scalar_one.return_value = annotation
        # second execute: fetch email
        email_result = MagicMock()
        email_result.scalar_one.return_value = "u@t.com"
        session.execute.side_effect = [scalar_result, email_result]

        updated = await update_annotation(
            session,
            _ANNO_ID,
            {"content": "new content", "type": None},
        )
        assert updated.content == "new content"
        # type stays because none values are skipped
        assert updated.type == "observation"
        session.commit.assert_awaited_once()
        assert updated.created_by_email == "u@t.com"

    @pytest.mark.asyncio
    async def test_refresh_called(self) -> None:
        """commits and refreshes the annotation."""
        session = _mock_session()
        annotation = Annotation(
            case_id=UUID(_CASE_ID),
            type="note",
            content="x",
            created_by=UUID(_USER_ID),
        )
        scalar_result = MagicMock()
        scalar_result.scalar_one.return_value = annotation
        email_result = MagicMock()
        email_result.scalar_one.return_value = "u@t.com"
        session.execute.side_effect = [scalar_result, email_result]

        await update_annotation(session, _ANNO_ID, {"content": "y"})
        session.refresh.assert_awaited_once_with(annotation)


# ── update_annotation field whitelist ─────────────────────


class TestUpdateAnnotationFieldWhitelist:
    @pytest.mark.asyncio
    async def test_rejects_non_updatable_field(self) -> None:
        """setattr rejects fields not in whitelist."""
        session = _mock_session()
        annotation = Annotation(
            case_id=UUID(_CASE_ID),
            type="note",
            content="x",
            created_by=UUID(_USER_ID),
        )
        scalar_result = MagicMock()
        scalar_result.scalar_one.return_value = annotation
        session.execute.return_value = scalar_result

        with pytest.raises(ValueError, match="not updatable"):
            await update_annotation(
                session, _ANNO_ID, {"id": "evil"}
            )

    @pytest.mark.asyncio
    async def test_rejects_created_by(self) -> None:
        """cannot overwrite created_by via update."""
        session = _mock_session()
        annotation = Annotation(
            case_id=UUID(_CASE_ID),
            type="note",
            content="x",
            created_by=UUID(_USER_ID),
        )
        scalar_result = MagicMock()
        scalar_result.scalar_one.return_value = annotation
        session.execute.return_value = scalar_result

        with pytest.raises(ValueError, match="not updatable"):
            await update_annotation(
                session, _ANNO_ID, {"created_by": "evil"}
            )

    @pytest.mark.asyncio
    async def test_rejects_case_id(self) -> None:
        """cannot change case_id via update."""
        session = _mock_session()
        annotation = Annotation(
            case_id=UUID(_CASE_ID),
            type="note",
            content="x",
            created_by=UUID(_USER_ID),
        )
        scalar_result = MagicMock()
        scalar_result.scalar_one.return_value = annotation
        session.execute.return_value = scalar_result

        with pytest.raises(ValueError, match="not updatable"):
            await update_annotation(
                session, _ANNO_ID, {"case_id": str(uuid4())}
            )

    @pytest.mark.asyncio
    async def test_allows_content_update(self) -> None:
        """content is in the whitelist and should be accepted."""
        session = _mock_session()
        annotation = Annotation(
            case_id=UUID(_CASE_ID),
            type="note",
            content="old",
            created_by=UUID(_USER_ID),
        )
        scalar_result = MagicMock()
        scalar_result.scalar_one.return_value = annotation
        email_result = MagicMock()
        email_result.scalar_one.return_value = "u@t.com"
        session.execute.side_effect = [scalar_result, email_result]

        updated = await update_annotation(
            session, _ANNO_ID, {"content": "new"}
        )
        assert updated.content == "new"

    @pytest.mark.asyncio
    async def test_whitelist_is_frozen(self) -> None:
        """whitelist must be a frozenset to prevent mutation."""
        assert isinstance(_UPDATABLE_ANNOTATION_FIELDS, frozenset)


# ── delete_annotation ──────────────────────────────────────


class TestDeleteAnnotation:
    @pytest.mark.asyncio
    async def test_deletes_existing(self) -> None:
        """returns true and deletes when found."""
        session = _mock_session()
        annotation = Annotation(
            case_id=UUID(_CASE_ID),
            type="note",
            content="x",
            created_by=UUID(_USER_ID),
        )
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = annotation
        session.execute.return_value = mock_result

        assert await delete_annotation(session, _ANNO_ID) is True
        session.delete.assert_awaited_once_with(annotation)
        session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_returns_false_when_missing(self) -> None:
        """returns false when annotation not found."""
        session = _mock_session()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute.return_value = mock_result

        assert await delete_annotation(session, _ANNO_ID) is False
        session.delete.assert_not_awaited()
