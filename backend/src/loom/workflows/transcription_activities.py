import logging
from typing import Any

from temporalio import activity

logger = logging.getLogger(__name__)


@activity.defn
async def extract_audio(asset_id: str) -> str:
    """download asset from minio, extract audio track.

    if asset is already audio, returns its path directly.
    currently a stub that returns a placeholder path.
    """
    logger.info("extracting audio for asset %s", asset_id)
    # TODO: full implementation
    # 1. fetch asset record from db
    # 2. download from minio to temp file
    # 3. check mime_type; if audio/*, return path directly
    # 4. if video/*, run ffmpeg to extract audio:
    #    subprocess.run(["ffmpeg", "-i", input, "-vn",
    #      "-acodec", "pcm_s16le", "-ar", "16000", output])
    # 5. return temp audio path
    return f"/tmp/loom/{asset_id}/audio.wav"  # noqa: S108


@activity.defn
async def transcribe_asset(
    asset_id: str,
    audio_path: str,
) -> list[dict[str, Any]]:
    """run transcription service on extracted audio.

    currently a stub that returns an empty segment list.
    """
    logger.info(
        "transcribing asset %s from %s",
        asset_id,
        audio_path,
    )
    # TODO: full implementation
    # 1. call transcribe_audio(audio_path)
    # 2. cache segments in workflow state or temp storage
    return []


@activity.defn
async def diarize_asset(
    asset_id: str,
    audio_path: str,
) -> list[dict[str, Any]]:
    """run speaker diarization and align with transcript.

    currently a stub that returns an empty list.
    """
    logger.info(
        "diarizing asset %s from %s",
        asset_id,
        audio_path,
    )
    # TODO: full implementation
    # 1. call diarize_audio(audio_path)
    # 2. fetch existing transcript segments
    # 3. call align_transcript_with_speakers
    # 4. update segments with speaker labels
    return []


@activity.defn
async def store_transcript(asset_id: str) -> None:
    """store transcript segments in db and create derivative.

    currently a stub.
    """
    logger.info("storing transcript for asset %s", asset_id)
    # TODO: full implementation
    # 1. fetch cached segments from workflow state
    # 2. call store_transcript_segments(session, asset_id, segs)
    # 3. create a Derivative record (type="transcript")
