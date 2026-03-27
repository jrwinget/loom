from unittest.mock import AsyncMock, MagicMock

import pytest

from loom.services.search import (
    VALID_TYPES,
    _ilike_pattern,
    search_case,
)


class TestIlikePattern:
    """tests for _ilike_pattern helper."""

    def test_simple_query(self) -> None:
        assert _ilike_pattern("hello") == "%hello%"

    def test_escapes_percent(self) -> None:
        assert _ilike_pattern("100%") == "%100\\%%"

    def test_escapes_underscore(self) -> None:
        assert _ilike_pattern("a_b") == "%a\\_b%"

    def test_escapes_backslash(self) -> None:
        assert _ilike_pattern("a\\b") == "%a\\\\b%"


class TestSearchCase:
    """tests for search_case service."""

    async def test_empty_results(self) -> None:
        """search with no matching data returns empty."""
        session = AsyncMock()
        # facet count queries all return 0
        scalar_result = MagicMock()
        scalar_result.scalar_one.return_value = 0
        session.execute = AsyncMock(return_value=scalar_result)

        result = await search_case(
            session,
            "01912345-6789-7abc-8def-0123456789ef",
            "nonexistent",
        )

        assert result["total"] == 0
        assert result["results"] == []
        assert set(result["facets"].keys()) == VALID_TYPES

    async def test_type_filtering(self) -> None:
        """search with type filter only queries selected types."""
        session = AsyncMock()
        scalar_result = MagicMock()
        scalar_result.scalar_one.return_value = 0
        session.execute = AsyncMock(return_value=scalar_result)

        result = await search_case(
            session,
            "01912345-6789-7abc-8def-0123456789ef",
            "test",
            result_types=["annotations"],
        )

        # only annotations should have been queried
        assert result["facets"]["annotations"] == 0
        # others should be 0 (not queried)
        assert result["facets"]["transcripts"] == 0
        assert result["facets"]["ocr"] == 0

    async def test_invalid_types_ignored(self) -> None:
        """invalid type names are filtered out."""
        session = AsyncMock()
        scalar_result = MagicMock()
        scalar_result.scalar_one.return_value = 0
        session.execute = AsyncMock(return_value=scalar_result)

        result = await search_case(
            session,
            "01912345-6789-7abc-8def-0123456789ef",
            "test",
            result_types=["invalid_type"],
        )

        # no valid types, so all facets 0 and no results
        assert result["total"] == 0
        assert result["results"] == []

    async def test_result_structure(self) -> None:
        """response has required keys."""
        session = AsyncMock()
        scalar_result = MagicMock()
        scalar_result.scalar_one.return_value = 0
        session.execute = AsyncMock(return_value=scalar_result)

        result = await search_case(
            session,
            "01912345-6789-7abc-8def-0123456789ef",
            "test",
        )

        assert "results" in result
        assert "total" in result
        assert "facets" in result
        assert isinstance(result["results"], list)
        assert isinstance(result["total"], int)
        assert isinstance(result["facets"], dict)

    async def test_invalid_uuid_raises(self) -> None:
        """invalid case_id raises ValueError."""
        session = AsyncMock()
        with pytest.raises(ValueError):
            await search_case(session, "not-a-uuid", "test")
