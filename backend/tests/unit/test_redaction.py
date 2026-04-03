from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest

from loom.models.redaction import Redaction
from loom.services.redaction import (
    apply_image_redaction,
    apply_redaction,
    create_redaction,
    get_redaction,
    get_redactions,
    mute_audio_regions,
)

FAKE_ASSET_ID = "01912345-6789-7abc-8def-012345678901"
FAKE_USER_ID = "01912345-6789-7abc-8def-012345678902"
FAKE_REDACTION_ID = "01912345-6789-7abc-8def-012345678903"


class TestCreateRedaction:
    """tests for create_redaction service function."""

    async def test_creates_pending_record(self) -> None:
        """creates a redaction with pending status."""
        session = AsyncMock()
        regions = [{"type": "rect", "x": 0.1, "y": 0.1, "w": 0.3, "h": 0.3}]

        result = await create_redaction(
            session,
            FAKE_ASSET_ID,
            FAKE_USER_ID,
            "blur",
            regions,
        )

        assert isinstance(result, Redaction)
        assert result.asset_id == UUID(FAKE_ASSET_ID)
        assert result.redacted_by == UUID(FAKE_USER_ID)
        assert result.redaction_type == "blur"
        assert result.regions == regions
        assert result.status == "pending"
        session.add.assert_called_once_with(result)
        session.flush.assert_called_once()

    async def test_creates_black_box_type(self) -> None:
        """supports black_box redaction type."""
        session = AsyncMock()
        regions = [{"type": "rect", "x": 0.0, "y": 0.0, "w": 0.5, "h": 0.5}]

        result = await create_redaction(
            session,
            FAKE_ASSET_ID,
            FAKE_USER_ID,
            "black_box",
            regions,
        )

        assert result.redaction_type == "black_box"

    async def test_creates_audio_mute_type(self) -> None:
        """supports audio_mute redaction type."""
        session = AsyncMock()
        regions = [{"type": "temporal", "start_time": 1.0, "end_time": 5.0}]

        result = await create_redaction(
            session,
            FAKE_ASSET_ID,
            FAKE_USER_ID,
            "audio_mute",
            regions,
        )

        assert result.redaction_type == "audio_mute"


class TestGetRedactions:
    """tests for get_redactions service function."""

    async def test_returns_paginated_list(self) -> None:
        """returns items and total count."""
        mock_redaction = MagicMock(spec=Redaction)
        mock_redaction.asset_id = UUID(FAKE_ASSET_ID)

        # mock count query
        count_result = MagicMock()
        count_result.scalar_one.return_value = 1

        # mock list query
        list_result = MagicMock()
        list_result.scalars.return_value.all.return_value = [mock_redaction]

        session = AsyncMock()
        session.execute = AsyncMock(side_effect=[count_result, list_result])

        items, total = await get_redactions(
            session, FAKE_ASSET_ID, skip=0, limit=20
        )

        assert total == 1
        assert len(items) == 1
        assert items[0] == mock_redaction

    async def test_empty_list(self) -> None:
        """returns empty list when no redactions exist."""
        count_result = MagicMock()
        count_result.scalar_one.return_value = 0

        list_result = MagicMock()
        list_result.scalars.return_value.all.return_value = []

        session = AsyncMock()
        session.execute = AsyncMock(side_effect=[count_result, list_result])

        items, total = await get_redactions(session, FAKE_ASSET_ID)

        assert total == 0
        assert items == []


class TestGetRedaction:
    """tests for get_redaction service function."""

    async def test_returns_redaction(self) -> None:
        """returns redaction when found."""
        mock_redaction = MagicMock(spec=Redaction)
        result = MagicMock()
        result.scalar_one_or_none.return_value = mock_redaction

        session = AsyncMock()
        session.execute = AsyncMock(return_value=result)

        redaction = await get_redaction(session, FAKE_REDACTION_ID)

        assert redaction == mock_redaction

    async def test_returns_none_when_missing(self) -> None:
        """returns none when redaction not found."""
        result = MagicMock()
        result.scalar_one_or_none.return_value = None

        session = AsyncMock()
        session.execute = AsyncMock(return_value=result)

        redaction = await get_redaction(session, FAKE_REDACTION_ID)

        assert redaction is None


class TestApplyImageRedaction:
    """tests for apply_image_redaction with mock pillow."""

    def _make_mock_image(self) -> tuple[MagicMock, MagicMock]:
        """create mock image and module objects."""
        mock_img = MagicMock()
        mock_img.size = (100, 100)
        mock_cropped = MagicMock()
        mock_img.crop.return_value = mock_cropped
        mock_blurred = MagicMock()
        mock_cropped.filter.return_value = mock_blurred
        mock_small = MagicMock()
        mock_cropped.resize.return_value = mock_small
        mock_pixelated = MagicMock()
        mock_small.resize.return_value = mock_pixelated
        return mock_img, mock_cropped

    def test_black_box_redaction(self) -> None:
        """applies black rectangle over region."""
        mock_img, _ = self._make_mock_image()
        mock_draw = MagicMock()

        regions = [{"type": "rect", "x": 0.1, "y": 0.1, "w": 0.5, "h": 0.5}]

        with (
            patch("loom.services.redaction._HAS_PILLOW", True),
            patch("loom.services.redaction.Image", create=True) as mock_pil,
            patch(
                "loom.services.redaction.ImageDraw",
                create=True,
            ) as mock_draw_mod,
        ):
            mock_pil.open.return_value = mock_img
            mock_draw_mod.Draw.return_value = mock_draw
            # mock save to write bytes
            mock_img.save.side_effect = lambda buf, format: buf.write(
                b"PNG-DATA"
            )

            result = apply_image_redaction(b"fake-png", regions, "black_box")

        assert result is not None
        assert result == b"PNG-DATA"
        mock_draw.rectangle.assert_called_once()

    def test_blur_redaction(self) -> None:
        """applies gaussian blur over region."""
        mock_img, _cropped = self._make_mock_image()

        regions = [{"type": "rect", "x": 0.2, "y": 0.2, "w": 0.3, "h": 0.3}]

        with (
            patch("loom.services.redaction._HAS_PILLOW", True),
            patch("loom.services.redaction.Image", create=True) as mock_pil,
            patch("loom.services.redaction.ImageFilter", create=True),
        ):
            mock_pil.open.return_value = mock_img
            mock_img.save.side_effect = lambda buf, format: buf.write(
                b"BLUR-DATA"
            )

            result = apply_image_redaction(b"fake-png", regions, "blur")

        assert result is not None
        mock_img.crop.assert_called_once()
        mock_img.paste.assert_called_once()

    def test_pixelate_redaction(self) -> None:
        """applies pixelation over region."""
        mock_img, _cropped = self._make_mock_image()

        regions = [{"type": "rect", "x": 0.0, "y": 0.0, "w": 0.5, "h": 0.5}]

        with (
            patch("loom.services.redaction._HAS_PILLOW", True),
            patch("loom.services.redaction.Image", create=True) as mock_pil,
        ):
            mock_pil.open.return_value = mock_img
            mock_pil.NEAREST = 0
            mock_img.save.side_effect = lambda buf, format: buf.write(
                b"PIX-DATA"
            )

            result = apply_image_redaction(b"fake-png", regions, "pixelate")

        assert result is not None
        mock_img.crop.assert_called_once()

    def test_circle_region_type_supported(self) -> None:
        """circle regions are processed (same as rect box)."""
        mock_img, _ = self._make_mock_image()
        mock_draw = MagicMock()

        regions = [
            {
                "type": "circle",
                "x": 0.2,
                "y": 0.2,
                "w": 0.4,
                "h": 0.4,
            }
        ]

        with (
            patch("loom.services.redaction._HAS_PILLOW", True),
            patch("loom.services.redaction.Image", create=True) as mock_pil,
            patch(
                "loom.services.redaction.ImageDraw",
                create=True,
            ) as mock_draw_mod,
        ):
            mock_pil.open.return_value = mock_img
            mock_draw_mod.Draw.return_value = mock_draw
            mock_img.save.side_effect = lambda buf, format: buf.write(b"CIRCLE")

            result = apply_image_redaction(b"fake-png", regions, "black_box")

        assert result is not None
        mock_draw.rectangle.assert_called_once()

    def test_temporal_region_skipped(self) -> None:
        """temporal regions are ignored for image redaction."""
        mock_img, _ = self._make_mock_image()

        regions = [{"type": "temporal", "start_time": 0, "end_time": 5}]

        with (
            patch("loom.services.redaction._HAS_PILLOW", True),
            patch("loom.services.redaction.Image", create=True) as mock_pil,
        ):
            mock_pil.open.return_value = mock_img
            mock_img.save.side_effect = lambda buf, format: buf.write(
                b"UNCHANGED"
            )

            result = apply_image_redaction(b"fake-png", regions, "blur")

        # should return image bytes without modification
        assert result is not None
        mock_img.crop.assert_not_called()


class TestGracefulDegradation:
    """tests for graceful degradation when pillow is missing."""

    def test_returns_none_without_pillow(self) -> None:
        """returns none when pillow is not available."""
        with patch("loom.services.redaction._HAS_PILLOW", False):
            result = apply_image_redaction(
                b"fake-image-data",
                [{"type": "rect", "x": 0, "y": 0, "w": 1, "h": 1}],
                "blur",
            )

        assert result is None


class TestApplyRedaction:
    """tests for the apply_redaction orchestrator."""

    async def test_image_redaction_no_bytes_fails(
        self,
    ) -> None:
        """fails when image bytes not provided."""
        session = AsyncMock()
        redaction = MagicMock(spec=Redaction)
        redaction.redaction_type = "blur"
        redaction.regions = [{"type": "rect", "x": 0, "y": 0, "w": 1, "h": 1}]

        result = await apply_redaction(session, redaction, image_bytes=None)

        assert result.status == "failed"
        assert "no image data" in result.error_message

    async def test_image_redaction_no_pillow_fails(
        self,
    ) -> None:
        """fails gracefully when pillow not installed."""
        session = AsyncMock()
        redaction = MagicMock(spec=Redaction)
        redaction.redaction_type = "black_box"
        redaction.regions = [{"type": "rect", "x": 0, "y": 0, "w": 1, "h": 1}]

        with patch("loom.services.redaction._HAS_PILLOW", False):
            result = await apply_redaction(
                session, redaction, image_bytes=b"fake"
            )

        assert result.status == "failed"
        assert "pillow" in result.error_message

    async def test_image_redaction_uploads_to_storage(
        self,
    ) -> None:
        """successful image redaction uploads derivative."""
        session = AsyncMock()
        storage = MagicMock()
        redaction = MagicMock(spec=Redaction)
        redaction.redaction_type = "blur"
        redaction.asset_id = UUID(FAKE_ASSET_ID)
        redaction.id = UUID(FAKE_REDACTION_ID)
        redaction.regions = [
            {"type": "rect", "x": 0, "y": 0, "w": 1, "h": 1}
        ]

        with patch(
            "loom.services.redaction.apply_image_redaction",
            return_value=b"redacted-png",
        ):
            result = await apply_redaction(
                session, redaction,
                image_bytes=b"original",
                storage=storage,
            )

        assert result.status == "complete"
        assert result.output_storage_key is not None
        storage.upload_bytes.assert_called_once()
        call_args = storage.upload_bytes.call_args
        assert call_args[0][0] == "loom-derivatives"
        assert call_args[0][2] == b"redacted-png"

    async def test_audio_mute_fails_without_storage(
        self,
    ) -> None:
        """audio mute fails when no storage provided."""
        session = AsyncMock()
        redaction = MagicMock(spec=Redaction)
        redaction.redaction_type = "audio_mute"
        redaction.regions = [
            {"type": "temporal", "start_time": 0, "end_time": 5}
        ]

        result = await apply_redaction(session, redaction)

        assert result.status == "failed"
        assert "storage" in result.error_message

    async def test_unsupported_type_fails(self) -> None:
        """unknown redaction type sets failed status."""
        session = AsyncMock()
        redaction = MagicMock(spec=Redaction)
        redaction.redaction_type = "unknown_type"
        redaction.regions = []

        result = await apply_redaction(session, redaction)

        assert result.status == "failed"
        assert "unsupported" in result.error_message


class TestRedactionModel:
    """tests for the redaction model structure."""

    def test_model_has_required_fields(self) -> None:
        """redaction model has all expected columns."""
        redaction = Redaction(
            asset_id=UUID(FAKE_ASSET_ID),
            redacted_by=UUID(FAKE_USER_ID),
            redaction_type="blur",
            regions=[{"type": "rect", "x": 0, "y": 0, "w": 1, "h": 1}],
            status="pending",
        )

        assert redaction.asset_id == UUID(FAKE_ASSET_ID)
        assert redaction.redacted_by == UUID(FAKE_USER_ID)
        assert redaction.redaction_type == "blur"
        assert redaction.status == "pending"
        assert redaction.output_storage_key is None
        assert redaction.error_message is None

    def test_tablename(self) -> None:
        """model uses correct table name."""
        assert Redaction.__tablename__ == "redactions"


class TestRedactionSchemas:
    """tests for pydantic redaction schemas."""

    def test_redaction_create_valid(self) -> None:
        """valid create request parses correctly."""
        from loom.schemas.redaction import RedactionCreate

        data = {
            "redaction_type": "blur",
            "regions": [
                {"type": "rect", "x": 0.1, "y": 0.2, "w": 0.3, "h": 0.4}
            ],
        }
        schema = RedactionCreate(**data)
        assert schema.redaction_type == "blur"
        assert len(schema.regions) == 1

    def test_redaction_create_rejects_empty_regions(
        self,
    ) -> None:
        """create request requires at least one region."""
        from pydantic import ValidationError

        from loom.schemas.redaction import RedactionCreate

        with pytest.raises(ValidationError):
            RedactionCreate(
                redaction_type="blur",
                regions=[],
            )

    def test_redaction_create_rejects_invalid_type(
        self,
    ) -> None:
        """create request rejects unknown redaction type."""
        from pydantic import ValidationError

        from loom.schemas.redaction import RedactionCreate

        with pytest.raises(ValidationError):
            RedactionCreate(
                redaction_type="invalid",
                regions=[{"type": "rect", "x": 0, "y": 0, "w": 1, "h": 1}],
            )

    def test_redaction_region_temporal(self) -> None:
        """temporal region parses without spatial coords."""
        from loom.schemas.redaction import RedactionRegion

        region = RedactionRegion(
            type="temporal",
            start_time=1.5,
            end_time=3.0,
        )
        assert region.x is None
        assert region.start_time == 1.5

    def test_redaction_response_from_attributes(
        self,
    ) -> None:
        """response schema supports from_attributes mode."""
        from loom.schemas.redaction import RedactionResponse

        assert RedactionResponse.model_config["from_attributes"] is True


class TestMuteAudioRegions:
    """tests for mute_audio_regions ffmpeg wrapper."""

    def test_copies_file_when_no_valid_regions(
        self, tmp_path: Any
    ) -> None:
        """copies input to output when no regions apply."""
        input_file = tmp_path / "input.mp4"
        input_file.write_bytes(b"fake-video-data")
        output_file = tmp_path / "output.mp4"

        mute_audio_regions(
            str(input_file),
            str(output_file),
            [{"type": "temporal", "start_time": 5, "end_time": 3}],
        )

        assert output_file.read_bytes() == b"fake-video-data"

    def test_copies_file_when_empty_regions(
        self, tmp_path: Any
    ) -> None:
        """copies input when regions list is empty."""
        input_file = tmp_path / "input.mp4"
        input_file.write_bytes(b"fake-video-data")
        output_file = tmp_path / "output.mp4"

        mute_audio_regions(str(input_file), str(output_file), [])

        assert output_file.read_bytes() == b"fake-video-data"

    def test_raises_when_ffmpeg_not_found(self) -> None:
        """raises runtime error when ffmpeg is missing."""
        with patch("loom.services.redaction.shutil.which", return_value=None):
            with pytest.raises(RuntimeError, match="ffmpeg not found"):
                mute_audio_regions(
                    "/tmp/in.mp4",
                    "/tmp/out.mp4",
                    [{"start_time": 0, "end_time": 5}],
                )

    def test_raises_on_ffmpeg_failure(self) -> None:
        """raises runtime error on non-zero ffmpeg exit."""
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = b"error details"

        with (
            patch(
                "loom.services.redaction.shutil.which",
                return_value="/usr/bin/ffmpeg",
            ),
            patch(
                "loom.services.redaction.subprocess.run",
                return_value=mock_result,
            ),
        ):
            with pytest.raises(RuntimeError, match="exited with code 1"):
                mute_audio_regions(
                    "/tmp/in.mp4",
                    "/tmp/out.mp4",
                    [{"start_time": 0, "end_time": 5}],
                )

    def test_builds_correct_filter_chain(self) -> None:
        """builds volume filter for each valid region."""
        mock_result = MagicMock()
        mock_result.returncode = 0

        regions = [
            {"start_time": 1.0, "end_time": 3.0},
            {"start_time": 5.5, "end_time": 8.0},
        ]

        with (
            patch(
                "loom.services.redaction.shutil.which",
                return_value="/usr/bin/ffmpeg",
            ),
            patch(
                "loom.services.redaction.subprocess.run",
                return_value=mock_result,
            ) as mock_run,
        ):
            mute_audio_regions("/tmp/in.mp4", "/tmp/out.mp4", regions)

        cmd = mock_run.call_args[0][0]
        assert cmd[0] == "ffmpeg"
        assert "-af" in cmd
        af_idx = cmd.index("-af")
        af_value = cmd[af_idx + 1]
        assert "between(t,1.0,3.0)" in af_value
        assert "between(t,5.5,8.0)" in af_value
        assert af_value.count("volume=enable=") == 2
