import base64
import logging
import mimetypes
from pathlib import Path
from typing import Any
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from loom.models.transcript import TranscriptSegment
from loom.services.ai_providers import GEMINI, transport_for
from loom.services.model_metadata import (
    UNKNOWN_VERSION,
    build_provenance,
)

# gemini's inline-data path caps the request body (~20MB); base64 adds
# ~33%, so guard the raw file a little under that. larger files need the
# files-api upload path (a follow-up).
_GEMINI_INLINE_MAX_BYTES = 15 * 1024 * 1024

logger = logging.getLogger(__name__)

# generous ceiling: a long recording transcribed by a cloud api.
_CLOUD_TIMEOUT_S = 300.0

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


def _cloud_provenance(
    provider: str, model: str, base_url: str
) -> dict[str, Any]:
    return {
        "model_name": f"cloud:{model}",
        "model_version": "api",
        "model_params": {
            "provider": provider or "cloud",
            "endpoint": httpx.URL(base_url).host,
            "model": model,
        },
    }


async def transcribe_via_cloud(
    file_path: str,
    *,
    provider: str = "",
    base_url: str,
    api_key: str,
    model: str,
) -> list[dict[str, Any]]:
    """transcribe a file via the cloud, dispatching on the provider.

    sends the original file (audio or video) directly — the api
    extracts audio server-side — so no local ffmpeg is required.
    returns segments in the same shape as :func:`transcribe_audio`,
    with provenance marking the cloud provider and endpoint.
    """
    if transport_for(provider) == GEMINI:
        return await _transcribe_gemini(
            file_path,
            provider=provider,
            base_url=base_url,
            api_key=api_key,
            model=model,
        )
    return await _transcribe_openai_audio(
        file_path,
        provider=provider,
        base_url=base_url,
        api_key=api_key,
        model=model,
    )


async def _transcribe_openai_audio(
    file_path: str,
    *,
    provider: str,
    base_url: str,
    api_key: str,
    model: str,
) -> list[dict[str, Any]]:
    """OpenAI-compatible /audio/transcriptions (OpenAI, self-hosted)."""
    endpoint = base_url.rstrip("/") + "/audio/transcriptions"
    provenance = _cloud_provenance(provider, model, base_url)

    with Path(file_path).open("rb") as fh:
        files = {"file": (Path(file_path).name, fh)}
        data = {"model": model, "response_format": "verbose_json"}
        headers = {"Authorization": f"Bearer {api_key}"}
        async with httpx.AsyncClient(timeout=_CLOUD_TIMEOUT_S) as client:
            resp = await client.post(
                endpoint, files=files, data=data, headers=headers
            )
    resp.raise_for_status()
    body = resp.json()

    language = body.get("language")
    segments = body.get("segments") or []
    results: list[dict[str, Any]] = [
        {
            "start": float(seg.get("start", 0.0)),
            "end": float(seg.get("end", 0.0)),
            "text": (seg.get("text") or "").strip(),
            "language": language,
            "confidence": seg.get("avg_logprob"),
            **provenance,
        }
        for seg in segments
    ]
    # some endpoints return text-only (no segments) — keep the result.
    if not results and body.get("text"):
        results.append(
            {
                "start": 0.0,
                "end": 0.0,
                "text": str(body["text"]).strip(),
                "language": language,
                "confidence": None,
                **provenance,
            }
        )
    return results


def _gemini_transcript_text(body: dict[str, Any]) -> str:
    """pull the transcript text out of a generateContent response."""
    candidates = body.get("candidates") or []
    if not candidates:
        return ""
    parts = (candidates[0].get("content") or {}).get("parts") or []
    return "".join(str(p.get("text", "")) for p in parts).strip()


async def _transcribe_gemini(
    file_path: str,
    *,
    provider: str,
    base_url: str,
    api_key: str,
    model: str,
) -> list[dict[str, Any]]:
    """Gemini generateContent with inline audio.

    gemini returns prose, not timed segments, so the transcript lands as
    a single segment. inline data caps request size; larger files need
    the files-api upload path (not yet wired).
    """
    raw = Path(file_path).read_bytes()
    if len(raw) > _GEMINI_INLINE_MAX_BYTES:
        raise ValueError(
            "file too large for the Gemini inline transcription path "
            f"({len(raw)} bytes > {_GEMINI_INLINE_MAX_BYTES})"
        )
    mime = mimetypes.guess_type(file_path)[0] or "audio/mpeg"
    endpoint = f"{base_url.rstrip('/')}/models/{model}:generateContent"
    request = {
        "contents": [
            {
                "parts": [
                    {
                        "inline_data": {
                            "mime_type": mime,
                            "data": base64.b64encode(raw).decode("ascii"),
                        }
                    },
                    {
                        "text": (
                            "Transcribe this recording verbatim. Return "
                            "only the transcript text, with no commentary."
                        )
                    },
                ]
            }
        ]
    }
    headers = {"x-goog-api-key": api_key}
    async with httpx.AsyncClient(timeout=_CLOUD_TIMEOUT_S) as client:
        resp = await client.post(endpoint, json=request, headers=headers)
    resp.raise_for_status()

    text = _gemini_transcript_text(resp.json())
    if not text:
        return []
    return [
        {
            "start": 0.0,
            "end": 0.0,
            "text": text,
            "language": None,
            "confidence": None,
            **_cloud_provenance(provider, model, base_url),
        }
    ]


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
