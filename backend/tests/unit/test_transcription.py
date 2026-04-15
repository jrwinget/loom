from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from loom.services.transcription import (
    align_transcript_with_speakers,
    diarize_audio,
    store_transcript_segments,
    transcribe_audio,
)


class TestAlignTranscriptWithSpeakers:
    """tests for align_transcript_with_speakers."""

    def test_empty_diarization_returns_segments(self) -> None:
        segments = [
            {"start": 0.0, "end": 5.0, "text": "hello"},
        ]
        result = align_transcript_with_speakers(segments, [])
        assert result == segments

    def test_assigns_speaker_with_most_overlap(self) -> None:
        segments = [
            {"start": 0.0, "end": 10.0, "text": "hello"},
        ]
        diarization = [
            {"speaker": "SPEAKER_0", "start": 0.0, "end": 3.0},
            {"speaker": "SPEAKER_1", "start": 3.0, "end": 10.0},
        ]
        result = align_transcript_with_speakers(segments, diarization)
        assert len(result) == 1
        # speaker_1 has 7s overlap vs speaker_0's 3s
        assert result[0]["speaker_label"] == "SPEAKER_1"

    def test_multiple_segments(self) -> None:
        segments = [
            {"start": 0.0, "end": 5.0, "text": "first"},
            {"start": 5.0, "end": 10.0, "text": "second"},
        ]
        diarization = [
            {"speaker": "A", "start": 0.0, "end": 6.0},
            {"speaker": "B", "start": 6.0, "end": 10.0},
        ]
        result = align_transcript_with_speakers(segments, diarization)
        assert result[0]["speaker_label"] == "A"
        assert result[1]["speaker_label"] == "B"

    def test_no_overlap_returns_none_speaker(self) -> None:
        segments = [
            {"start": 20.0, "end": 25.0, "text": "late"},
        ]
        diarization = [
            {"speaker": "A", "start": 0.0, "end": 5.0},
        ]
        result = align_transcript_with_speakers(segments, diarization)
        assert result[0]["speaker_label"] is None

    def test_preserves_original_segment_data(self) -> None:
        segments = [
            {
                "start": 0.0,
                "end": 5.0,
                "text": "hello",
                "language": "en",
                "confidence": 0.9,
            },
        ]
        diarization = [
            {"speaker": "X", "start": 0.0, "end": 5.0},
        ]
        result = align_transcript_with_speakers(segments, diarization)
        assert result[0]["text"] == "hello"
        assert result[0]["language"] == "en"
        assert result[0]["confidence"] == 0.9
        assert result[0]["speaker_label"] == "X"


class TestStoreTranscriptSegments:
    """tests for store_transcript_segments."""

    @pytest.mark.asyncio
    async def test_creates_records(self) -> None:
        session = AsyncMock()
        session.add = MagicMock()
        session.flush = AsyncMock()

        segments = [
            {
                "start": 0.0,
                "end": 5.0,
                "text": "hello",
                "language": "en",
                "confidence": 0.95,
                "speaker_label": "SPEAKER_0",
            },
            {
                "start": 5.0,
                "end": 10.0,
                "text": "world",
                "language": "en",
                "confidence": 0.88,
            },
        ]

        asset_id = "01912345-6789-7abc-8def-0123456789ab"
        records = await store_transcript_segments(session, asset_id, segments)

        assert len(records) == 2
        assert session.add.call_count == 2
        session.flush.assert_awaited_once()

        assert records[0].text == "hello"
        assert records[0].speaker_label == "SPEAKER_0"
        assert records[1].text == "world"
        assert records[1].speaker_label is None


class TestTranscribeAudio:
    """tests for transcribe_audio graceful fallback."""

    def test_missing_faster_whisper_returns_stub(
        self,
    ) -> None:
        with patch.dict("sys.modules", {"faster_whisper": None}):
            result = transcribe_audio("/fake/path.wav")

        assert len(result) == 1
        assert "unavailable" in result[0]["text"]

    def test_with_faster_whisper_installed(self) -> None:
        mock_segment = MagicMock()
        mock_segment.start = 0.0
        mock_segment.end = 5.0
        mock_segment.text = " hello world "
        mock_segment.avg_log_prob = 0.9

        mock_info = MagicMock()
        mock_info.language = "en"

        mock_model = MagicMock()
        mock_model.transcribe.return_value = (
            [mock_segment],
            mock_info,
        )

        mock_fw = MagicMock()
        mock_fw.WhisperModel.return_value = mock_model

        with patch.dict("sys.modules", {"faster_whisper": mock_fw}):
            result = transcribe_audio("/fake/path.wav")

        assert len(result) == 1
        assert result[0]["text"] == "hello world"
        assert result[0]["language"] == "en"


class TestDiarizeAudio:
    """tests for diarize_audio graceful fallback."""

    def test_missing_pyannote_returns_empty(self) -> None:
        with patch.dict(
            "sys.modules",
            {
                "pyannote": None,
                "pyannote.audio": None,
            },
        ):
            result = diarize_audio("/fake/path.wav")

        assert result == []
