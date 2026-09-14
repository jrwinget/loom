import json
import logging
from pathlib import Path
from typing import Any
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from loom.models.transcript import TranscriptSegment
from loom.services.ai_config import (
    assert_resolved_host_safe,
    read_capped_response,
    validate_endpoint,
)
from loom.services.ai_providers import get_provider
from loom.services.engines import (
    REMEDY_WHISPER,
    EngineUnavailableError,
)
from loom.services.model_metadata import build_provenance

logger = logging.getLogger(__name__)

# a long recording transcribed by a cloud/self-hosted api; generous but
# bounded so a hung peer can't hold a worker forever.
_CLOUD_TIMEOUT = httpx.Timeout(connect=5.0, read=300.0, write=60.0, pool=5.0)
# a self-hosted/custom endpoint is user-configured, not trusted: cap the
# response body we'll buffer rather than reading an unbounded stream
# from a hostile or misbehaving peer into memory.
_MAX_RESPONSE_BYTES = 25 * 1024 * 1024

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
    model_version, model_params. raises EngineUnavailableError when
    faster-whisper is not installed — a fabricated placeholder row
    would be worse than a visible failure on an evidence product.
    """
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise EngineUnavailableError("transcription", REMEDY_WHISPER) from exc

    # weights come exclusively from the pinned registry: passing the
    # local directory (not a size alias) keeps faster-whisper off the
    # network entirely — no implicit hub download, ever
    from loom.services.model_registry import get_spec, resolve_model_dir

    model_dir = resolve_model_dir(model_size)
    provenance = build_provenance(
        _WHISPER_MODEL_NAME,
        _WHISPER_PACKAGE,
        {
            "model_size": model_size,
            "compute_type": "int8",
            "model_revision": get_spec(model_size).revision,
        },
    )

    model = WhisperModel(str(model_dir), compute_type="int8")
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
    """transcribe a file via a self-hosted/custom OpenAI-compatible
    endpoint.

    sends the original file (audio or video) directly — the api
    extracts audio server-side — so no local ffmpeg is required.
    returns segments in the same shape as :func:`transcribe_audio`, with
    provenance marking the endpoint used.

    re-validates the endpoint immediately before dispatch rather than
    trusting it was checked when saved (a config row can be written by a
    path other than the settings api) and resolves the hostname to catch
    a dns-rebinding attempt that a static url check alone can't see.
    """
    known = get_provider(provider) if provider else None
    # an empty provider is a pre-catalog config, treated as "custom".
    allow_local = known.base_url_editable if known else True
    validate_endpoint(base_url, allow_local=allow_local)
    assert_resolved_host_safe(base_url, allow_local=allow_local)
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
    """OpenAI-compatible /audio/transcriptions (self-hosted or custom)."""
    endpoint = base_url.rstrip("/") + "/audio/transcriptions"
    provenance = _cloud_provenance(provider, model, base_url)

    with Path(file_path).open("rb") as fh:
        files = {"file": (Path(file_path).name, fh)}
        data = {"model": model, "response_format": "verbose_json"}
        headers = {"Authorization": f"Bearer {api_key}"}
        async with (
            httpx.AsyncClient(
                timeout=_CLOUD_TIMEOUT, follow_redirects=False
            ) as client,
            client.stream(
                "POST", endpoint, files=files, data=data, headers=headers
            ) as resp,
        ):
            resp.raise_for_status()
            raw = await read_capped_response(resp, _MAX_RESPONSE_BYTES)
    body = json.loads(raw)

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
    # newer pyannote annotates the pipeline output as a union that
    # includes streaming iterators; this pipeline always returns an
    # Annotation, so narrow by capability before using it
    diarization: Any = pipeline(audio_path)
    if not hasattr(diarization, "itertracks"):
        logger.warning("unexpected diarization output; skipping")
        return []
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
