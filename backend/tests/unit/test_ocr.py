import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest

from loom.services.ocr import (
    extract_key_frames,
    run_ocr_on_image,
    store_ocr_regions,
)


class TestExtractKeyFrames:
    """tests for extract_key_frames."""

    def test_missing_file_raises(self) -> None:
        with pytest.raises(ValueError, match="not found"):
            extract_key_frames("/nonexistent/video.mp4")

    def test_negative_interval_raises(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            f.write(b"\x00" * 100)
            path = f.name

        try:
            with pytest.raises(ValueError, match="must be positive"):
                extract_key_frames(path, interval_seconds=-1.0)
        finally:
            Path(path).unlink(missing_ok=True)

    def test_zero_interval_raises(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            f.write(b"\x00" * 100)
            path = f.name

        try:
            with pytest.raises(ValueError, match="must be positive"):
                extract_key_frames(path, interval_seconds=0.0)
        finally:
            Path(path).unlink(missing_ok=True)

    def test_ffmpeg_not_found_returns_empty(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            f.write(b"\x00" * 100)
            path = f.name

        try:
            with patch(
                "loom.services.ocr.subprocess.run",
                side_effect=FileNotFoundError("ffmpeg"),
            ):
                result = extract_key_frames(path)
                assert result == []
        finally:
            Path(path).unlink(missing_ok=True)


class TestRunOcrOnImage:
    """tests for run_ocr_on_image."""

    def test_missing_image_returns_empty(self) -> None:
        result = run_ocr_on_image("/nonexistent/image.png")
        assert result == []

    def test_pytesseract_not_installed_returns_empty(
        self,
    ) -> None:
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            f.write(b"\x89PNG" + b"\x00" * 100)
            path = f.name

        try:
            with patch.dict("sys.modules", {"pytesseract": None}):
                result = run_ocr_on_image(path)
                assert result == []
        finally:
            Path(path).unlink(missing_ok=True)

    def test_pillow_not_installed_returns_empty(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            f.write(b"\x89PNG" + b"\x00" * 100)
            path = f.name

        try:
            # ensure pytesseract is "available" but PIL is not
            mock_tess = MagicMock()
            with patch.dict(
                "sys.modules",
                {"pytesseract": mock_tess, "PIL": None},
            ):
                result = run_ocr_on_image(path)
                assert result == []
        finally:
            Path(path).unlink(missing_ok=True)

    def test_ocr_exception_returns_empty(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            f.write(b"\x89PNG" + b"\x00" * 100)
            path = f.name

        try:
            mock_tess = MagicMock()
            mock_pil = MagicMock()
            mock_image = MagicMock()
            mock_image.size = (100, 100)
            mock_pil.Image.open.return_value = mock_image
            mock_tess.image_to_data.side_effect = RuntimeError("ocr failed")
            with patch.dict(
                "sys.modules",
                {
                    "pytesseract": mock_tess,
                    "PIL": mock_pil,
                    "PIL.Image": mock_pil.Image,
                },
            ):
                result = run_ocr_on_image(path)
                assert result == []
        finally:
            Path(path).unlink(missing_ok=True)


class TestStoreOcrRegions:
    """tests for store_ocr_regions."""

    async def test_stores_regions(self) -> None:
        session = AsyncMock()
        session.add = MagicMock()
        session.flush = AsyncMock()

        regions = [
            {
                "text": "hello world",
                "confidence": 0.95,
                "bounding_box": {
                    "x": 0.1,
                    "y": 0.2,
                    "width": 0.3,
                    "height": 0.1,
                },
                "frame_number": None,
                "timestamp": None,
                "language": "eng",
            },
            {
                "text": "second region",
                "confidence": 0.80,
                "bounding_box": None,
                "frame_number": 5,
                "timestamp": 25.0,
            },
        ]

        asset_id = "01912345-6789-7abc-8def-012345678903"
        result = await store_ocr_regions(session, asset_id, regions)

        assert len(result) == 2
        assert session.add.call_count == 2
        session.flush.assert_awaited_once()

        # verify first record
        first = result[0]
        assert first.text == "hello world"
        assert first.confidence == 0.95
        assert first.asset_id == UUID(asset_id)

    async def test_empty_regions(self) -> None:
        session = AsyncMock()
        session.add = MagicMock()
        session.flush = AsyncMock()

        result = await store_ocr_regions(
            session,
            "01912345-6789-7abc-8def-012345678903",
            [],
        )

        assert result == []
        session.add.assert_not_called()
        session.flush.assert_awaited_once()

    async def test_persists_model_provenance(self) -> None:
        """model name/version/params flow from region dict to row."""
        session = AsyncMock()
        session.add = MagicMock()
        session.flush = AsyncMock()

        regions = [
            {
                "text": "abc",
                "confidence": 0.9,
                "bounding_box": None,
                "frame_number": None,
                "timestamp": None,
                "model_name": "pytesseract",
                "model_version": "0.3.10",
                "model_params": {"language": "eng"},
            },
        ]
        result = await store_ocr_regions(
            session,
            "01912345-6789-7abc-8def-012345678903",
            regions,
        )

        assert result[0].model_name == "pytesseract"
        assert result[0].model_version == "0.3.10"
        assert result[0].model_params == {"language": "eng"}


class TestOcrIlikeEscaping:
    """tests that ocr text search escapes ILIKE wildcards."""

    def test_ilike_pattern_escapes_percent(self) -> None:
        """literal % in search text is escaped."""
        from loom.services.search import _ilike_pattern

        result = _ilike_pattern("100%")
        assert result == "%100\\%%"
        # should not match arbitrary text after "100"
        assert "%" not in result.strip("%") or "\\%" in result

    def test_ilike_pattern_escapes_underscore(self) -> None:
        """literal _ in search text is escaped."""
        from loom.services.search import _ilike_pattern

        result = _ilike_pattern("a_b")
        assert result == "%a\\_b%"

    def test_ilike_pattern_escapes_backslash(self) -> None:
        """literal backslash in search text is escaped."""
        from loom.services.search import _ilike_pattern

        result = _ilike_pattern("a\\b")
        assert result == "%a\\\\b%"

    def test_ilike_pattern_combined_wildcards(self) -> None:
        """multiple wildcards are all escaped."""
        from loom.services.search import _ilike_pattern

        result = _ilike_pattern("50%_off\\deal")
        assert result == "%50\\%\\_off\\\\deal%"

    def test_ilike_pattern_no_wildcards_unchanged(self) -> None:
        """plain text passes through with only wrapping %."""
        from loom.services.search import _ilike_pattern

        result = _ilike_pattern("hello world")
        assert result == "%hello world%"
