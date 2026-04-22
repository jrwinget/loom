"""temporal activities for the transcription pipeline.

uses shared engine/session and delegates to transcription
service. ai dependencies (faster-whisper, pyannote) are
optional and degrade gracefully.
"""

import logging
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import select
from temporalio import activity

from loom.metrics import ingest_workflow_duration
from loom.models.asset import Asset
from loom.services.storage_backends import ORIGINALS_BUCKET
from loom.services.transcription import (
    align_transcript_with_speakers,
    diarize_audio,
    store_transcript_segments,
    transcribe_audio,
)
from loom.workflows.shared import get_db_session, get_storage_backend

logger = logging.getLogger(__name__)


@activity.defn
async def extract_audio(asset_id: str) -> str:
    """download asset from minio, extract audio track.

    if asset is already audio, downloads and returns path.
    if video, extracts audio via ffmpeg to wav. idempotent:
    re-running produces the same output.
    """
    start = time.monotonic()
    try:
        logger.info("extracting audio for asset %s", asset_id)

        async with get_db_session() as session:
            result = await session.execute(
                select(Asset).where(Asset.id == UUID(asset_id))
            )
            asset = result.scalar_one_or_none()
            if asset is None:
                msg = f"asset {asset_id} not found"
                raise ValueError(msg)

            storage = get_storage_backend()

            tmp_dir = tempfile.mkdtemp(prefix="loom_audio_")
            suffix = Path(asset.original_filename).suffix
            src = str(Path(tmp_dir) / f"original{suffix}")
            storage.download_file(
                ORIGINALS_BUCKET,
                asset.storage_key,
                src,
            )

            if asset.media_type == "audio":
                logger.info(
                    "asset %s is audio; using directly",
                    asset_id,
                )
                return src

            ffmpeg = shutil.which("ffmpeg")
            if ffmpeg is None:
                msg = "ffmpeg is not installed; cannot extract audio from video"
                raise RuntimeError(msg)

            audio_path = str(Path(tmp_dir) / "audio.wav")
            cmd = [
                ffmpeg,
                "-y",
                "-hide_banner",
                "-loglevel",
                "error",
                "-i",
                src,
                "-vn",
                "-acodec",
                "pcm_s16le",
                "-ar",
                "16000",
                audio_path,
            ]
            subprocess.run(  # noqa: S603
                cmd, check=True, capture_output=True
            )

        logger.info(
            "audio extracted for asset %s: %s",
            asset_id,
            audio_path,
        )
        return audio_path
    finally:
        duration = time.monotonic() - start
        ingest_workflow_duration.labels(activity="extract_audio").observe(
            duration
        )


@activity.defn
async def transcribe_asset(
    asset_id: str,
    audio_path: str,
) -> list[dict[str, Any]]:
    """run transcription service on extracted audio.

    delegates to transcription service which gracefully
    degrades if faster-whisper is not installed. idempotent:
    re-running produces the same segments.
    """
    start = time.monotonic()
    try:
        logger.info(
            "transcribing asset %s from %s",
            asset_id,
            audio_path,
        )

        segments = transcribe_audio(audio_path)

        logger.info(
            "transcribed %d segments for asset %s",
            len(segments),
            asset_id,
        )
        return segments
    finally:
        duration = time.monotonic() - start
        ingest_workflow_duration.labels(activity="transcribe").observe(duration)


@activity.defn
async def diarize_asset(
    asset_id: str,
    audio_path: str,
) -> list[dict[str, Any]]:
    """run speaker diarization and align with transcript.

    delegates to transcription service which gracefully
    degrades if pyannote is not installed. idempotent.
    """
    start = time.monotonic()
    try:
        logger.info(
            "diarizing asset %s from %s",
            asset_id,
            audio_path,
        )

        diarization = diarize_audio(audio_path)

        logger.info(
            "diarization found %d speaker turns for asset %s",
            len(diarization),
            asset_id,
        )
        return diarization
    finally:
        duration = time.monotonic() - start
        ingest_workflow_duration.labels(activity="diarize").observe(duration)


@activity.defn
async def store_transcript(asset_id: str) -> None:
    """run transcription, diarize, align, and store in db.

    this activity is self-contained: it re-downloads,
    transcribes, and stores. idempotent: re-running will
    re-insert segments.
    """
    start = time.monotonic()
    try:
        logger.info("storing transcript for asset %s", asset_id)

        async with get_db_session() as session:
            result = await session.execute(
                select(Asset).where(Asset.id == UUID(asset_id))
            )
            asset = result.scalar_one_or_none()
            if asset is None:
                msg = f"asset {asset_id} not found"
                raise ValueError(msg)

            storage = get_storage_backend()

            with tempfile.TemporaryDirectory(
                prefix="loom_transcript_"
            ) as tmp_dir:
                suffix = Path(asset.original_filename).suffix
                src = str(Path(tmp_dir) / f"original{suffix}")
                storage.download_file(
                    ORIGINALS_BUCKET,
                    asset.storage_key,
                    src,
                )

                if asset.media_type == "video":
                    ffmpeg = shutil.which("ffmpeg")
                    if ffmpeg is None:
                        logger.warning(
                            "ffmpeg unavailable; cannot "
                            "extract audio for transcript"
                        )
                        return
                    audio_path = str(Path(tmp_dir) / "audio.wav")
                    subprocess.run(  # noqa: S603
                        [
                            ffmpeg,
                            "-y",
                            "-hide_banner",
                            "-loglevel",
                            "error",
                            "-i",
                            src,
                            "-vn",
                            "-acodec",
                            "pcm_s16le",
                            "-ar",
                            "16000",
                            audio_path,
                        ],
                        check=True,
                        capture_output=True,
                    )
                else:
                    audio_path = src

                segments = transcribe_audio(audio_path)
                diarization = diarize_audio(audio_path)

                if diarization:
                    segments = align_transcript_with_speakers(
                        segments, diarization
                    )

            records = await store_transcript_segments(
                session, asset_id, segments
            )
            await session.commit()

        logger.info(
            "stored %d transcript segments for asset %s",
            len(records),
            asset_id,
        )
    finally:
        duration = time.monotonic() - start
        ingest_workflow_duration.labels(activity="store_transcript").observe(
            duration
        )
