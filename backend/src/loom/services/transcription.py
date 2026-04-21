import logging
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from loom.models.transcript import TranscriptSegment
from loom.services.model_metadata import (
    UNKNOWN_VERSION,
    build_provenance,
)

logger = logging.getLogger(__name__)

_WHISPER_PACKAGE = "faster-whisper"
_WHISPER_MODEL_NAME = "faster-whisper"
_PYANNOTE_PACKAGE = "pyannote.audio"
_PYANNOTE_MODEL_NAME = "pyannote/speaker-diarization-3.1"


def transcribe_audio(
    audio_path: str,
    model_size: str = "base",
) -> list[dict[str, Any]]:
    """transcribe audio using faster-whisper.

    returns list of segment dicts with keys:
    start, end, text, language, confidence, model_name,
    model_version, model_params. if faster-whisper is not
    installed, returns a stub result with 'unknown' provenance.
    """
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        logger.warning(
            "faster-whisper not installed; returning stub transcript"
        )
        return [
            {
                "start": 0.0,
                "end": 0.0,
                "text": "[transcription unavailable]",
                "language": None,
                "confidence": None,
                "model_name": _WHISPER_MODEL_NAME,
                "model_version": UNKNOWN_VERSION,
                "model_params": {"model_size": model_size},
            }
        ]

    provenance = build_provenance(
        _WHISPER_MODEL_NAME,
        _WHISPER_PACKAGE,
        {"model_size": model_size, "compute_type": "int8"},
    )

    model = WhisperModel(model_size, compute_type="int8")
    segments_iter, info = model.transcribe(audio_path)

    results: list[dict[str, Any]] = []
    for segment in segments_iter:
        results.append(
            {
                "start": segment.start,
                "end": segment.end,
                "text": segment.text.strip(),
                "language": info.language,
                "confidence": segment.avg_log_prob,
                **provenance,
            }
        )
    return results


def diarize_audio(audio_path: str) -> list[dict[str, Any]]:
    """run speaker diarization using pyannote.audio.

    returns list of dicts with keys: speaker, start, end,
    model_name, model_version. if pyannote is not installed,
    returns empty list.
    """
    try:
        from pyannote.audio import Pipeline
    except ImportError:
        logger.warning("pyannote.audio not installed; skipping diarization")
        return []

    pipeline = Pipeline.from_pretrained(
        "pyannote/speaker-diarization-3.1",
    )
    if pipeline is None:
        logger.warning("failed to load pyannote pipeline")
        return []
    diarization = pipeline(audio_path)
    provenance = build_provenance(_PYANNOTE_MODEL_NAME, _PYANNOTE_PACKAGE)

    results: list[dict[str, Any]] = []
    for turn, _, speaker in diarization.itertracks(
        yield_label=True,
    ):
        results.append(
            {
                "speaker": speaker,
                "start": turn.start,
                "end": turn.end,
                **provenance,
            }
        )
    return results


def align_transcript_with_speakers(
    segments: list[dict[str, Any]],
    diarization: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """merge transcript segments with speaker labels.

    for each transcript segment, assigns the speaker label
    with the greatest time overlap.
    """
    if not diarization:
        return segments

    aligned: list[dict[str, Any]] = []
    for seg in segments:
        seg_start = seg["start"]
        seg_end = seg["end"]
        best_speaker: str | None = None
        best_overlap = 0.0

        for d in diarization:
            overlap_start = max(seg_start, d["start"])
            overlap_end = min(seg_end, d["end"])
            overlap = max(0.0, overlap_end - overlap_start)

            if overlap > best_overlap:
                best_overlap = overlap
                best_speaker = d["speaker"]

        aligned.append({**seg, "speaker_label": best_speaker})
    return aligned


async def store_transcript_segments(
    session: AsyncSession,
    asset_id: str,
    segments: list[dict[str, Any]],
) -> list[TranscriptSegment]:
    """bulk insert transcript segments into the database."""
    records: list[TranscriptSegment] = []
    for seg in segments:
        record = TranscriptSegment(
            asset_id=UUID(asset_id),
            speaker_label=seg.get("speaker_label"),
            start_time=seg["start"],
            end_time=seg["end"],
            text=seg["text"],
            confidence=seg.get("confidence"),
            language=seg.get("language"),
            model_name=seg.get("model_name"),
            model_version=seg.get("model_version"),
            model_params=seg.get("model_params"),
        )
        session.add(record)
        records.append(record)
    await session.flush()
    return records


async def get_transcript_segments(
    session: AsyncSession,
    asset_id: str,
    *,
    speaker: str | None = None,
    start_time: float | None = None,
    end_time: float | None = None,
) -> list[TranscriptSegment]:
    """fetch transcript segments with optional filters."""
    stmt = (
        select(TranscriptSegment)
        .where(TranscriptSegment.asset_id == UUID(asset_id))
        .order_by(TranscriptSegment.start_time)
    )
    if speaker is not None:
        stmt = stmt.where(TranscriptSegment.speaker_label == speaker)
    if start_time is not None:
        stmt = stmt.where(TranscriptSegment.end_time >= start_time)
    if end_time is not None:
        stmt = stmt.where(TranscriptSegment.start_time <= end_time)
    result = await session.execute(stmt)
    return list(result.scalars().all())
