"""tests that workflow activities observe duration metrics."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_ASSET_ID = "01912345-6789-7abc-8def-0123456789ef"
_EXPORT_ID = "01912345-6789-7abc-8def-0123456789ab"
_CASE_ID = "01912345-6789-7abc-8def-0123456789ab"


def _make_asset(
    *,
    media_type: str = "video",
    sha256: str = "abc123",
    sha512: str = "def456",
) -> MagicMock:
    from uuid import UUID

    asset = MagicMock()
    asset.id = UUID(_ASSET_ID)
    asset.case_id = UUID(_CASE_ID)
    asset.storage_key = f"{_CASE_ID}/{_ASSET_ID}/test.mp4"
    asset.original_filename = "test.mp4"
    asset.media_type = media_type
    asset.mime_type = "video/mp4"
    asset.sha256_hash = sha256
    asset.sha512_hash = sha512
    asset.uploaded_by = UUID(_ASSET_ID)
    asset.processing_status = "pending"
    return asset


def _mock_session(asset: MagicMock) -> tuple[MagicMock, AsyncMock]:
    session = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = asset
    session.execute.return_value = result
    ctx = AsyncMock()
    ctx.__aenter__.return_value = session
    return ctx, session


class TestIngestActivityMetrics:
    """verify ingest activities observe the histogram."""

    @patch(
        "loom.workflows.ingest_activities"
        ".ingest_workflow_duration"
    )
    @patch(
        "loom.workflows.ingest_activities"
        ".get_minio_client"
    )
    @patch(
        "loom.workflows.ingest_activities"
        ".get_db_session"
    )
    @patch(
        "loom.workflows.ingest_activities"
        ".compute_hashes_from_file"
    )
    async def test_verify_hash_observes_metric(
        self,
        mock_hash: MagicMock,
        mock_session_ctx: MagicMock,
        mock_minio: MagicMock,
        mock_metric: MagicMock,
    ) -> None:
        from loom.workflows.ingest_activities import (
            verify_asset_hash,
        )

        asset = _make_asset(sha256="aaa", sha512="bbb")
        ctx, _session = _mock_session(asset)
        mock_session_ctx.return_value = ctx
        mock_hash.return_value = ("aaa", "bbb")

        with (
            patch(
                "loom.workflows.ingest_activities"
                ".StorageService"
            ),
            patch(
                "loom.workflows.ingest_activities.tempfile"
            ) as mock_tmp,
        ):
            mock_tmp.TemporaryDirectory.return_value.__enter__ = (
                MagicMock(return_value="/tmp/test")  # noqa: S108
            )
            mock_tmp.TemporaryDirectory.return_value.__exit__ = (
                MagicMock(return_value=False)
            )
            await verify_asset_hash(_ASSET_ID)

        mock_metric.labels.assert_called_with(
            activity="verify_hash"
        )
        mock_metric.labels.return_value.observe.assert_called_once()
        duration = (
            mock_metric.labels.return_value.observe.call_args[0][0]
        )
        assert duration > 0

    @patch(
        "loom.workflows.ingest_activities"
        ".ingest_workflow_duration"
    )
    @patch(
        "loom.workflows.ingest_activities"
        ".get_db_session"
    )
    async def test_mark_complete_observes_metric(
        self,
        mock_session_ctx: MagicMock,
        mock_metric: MagicMock,
    ) -> None:
        from loom.workflows.ingest_activities import (
            mark_asset_complete,
        )

        asset = _make_asset()
        ctx, _ = _mock_session(asset)
        mock_session_ctx.return_value = ctx

        await mark_asset_complete(_ASSET_ID)

        mock_metric.labels.assert_called_with(
            activity="mark_complete"
        )
        mock_metric.labels.return_value.observe.assert_called_once()
        duration = (
            mock_metric.labels.return_value.observe.call_args[0][0]
        )
        assert duration > 0

    @patch(
        "loom.workflows.ingest_activities"
        ".ingest_workflow_duration"
    )
    @patch(
        "loom.workflows.ingest_activities"
        ".get_db_session"
    )
    async def test_metric_observed_on_error(
        self,
        mock_session_ctx: MagicMock,
        mock_metric: MagicMock,
    ) -> None:
        """metric is still observed when activity raises."""
        from loom.workflows.ingest_activities import (
            mark_asset_complete,
        )

        session = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        session.execute.return_value = result
        ctx = AsyncMock()
        ctx.__aenter__.return_value = session
        mock_session_ctx.return_value = ctx

        with pytest.raises(ValueError, match="not found"):
            await mark_asset_complete(_ASSET_ID)

        mock_metric.labels.return_value.observe.assert_called_once()
        duration = (
            mock_metric.labels.return_value.observe.call_args[0][0]
        )
        assert duration > 0


class TestExportActivityMetrics:
    """verify export activity observes the histogram."""

    @patch(
        "loom.workflows.export_activities"
        ".ingest_workflow_duration"
    )
    @patch(
        "loom.workflows.export_activities"
        ".get_db_session"
    )
    async def test_build_export_observes_metric(
        self,
        mock_session_ctx: MagicMock,
        mock_metric: MagicMock,
    ) -> None:
        from loom.workflows.export_activities import (
            build_export,
        )

        session = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        session.execute.return_value = result
        ctx = AsyncMock()
        ctx.__aenter__.return_value = session
        mock_session_ctx.return_value = ctx

        await build_export(_EXPORT_ID)

        mock_metric.labels.assert_called_with(
            activity="export"
        )
        mock_metric.labels.return_value.observe.assert_called_once()
        duration = (
            mock_metric.labels.return_value.observe.call_args[0][0]
        )
        assert duration > 0


class TestOcrActivityMetrics:
    """verify ocr activities observe the histogram."""

    @patch(
        "loom.workflows.ocr_activities"
        ".ingest_workflow_duration"
    )
    @patch(
        "loom.workflows.ocr_activities"
        ".get_minio_client"
    )
    @patch(
        "loom.workflows.ocr_activities"
        ".get_db_session"
    )
    async def test_prepare_ocr_observes_metric(
        self,
        mock_session_ctx: MagicMock,
        mock_minio: MagicMock,
        mock_metric: MagicMock,
    ) -> None:
        from loom.workflows.ocr_activities import (
            prepare_ocr_input,
        )

        asset = _make_asset()
        ctx, _ = _mock_session(asset)
        mock_session_ctx.return_value = ctx

        with patch(
            "loom.workflows.ocr_activities.StorageService"
        ):
            await prepare_ocr_input(_ASSET_ID)

        mock_metric.labels.assert_called_with(
            activity="ocr_prepare"
        )
        mock_metric.labels.return_value.observe.assert_called_once()
        duration = (
            mock_metric.labels.return_value.observe.call_args[0][0]
        )
        assert duration > 0


class TestSceneActivityMetrics:
    """verify scene activities observe the histogram."""

    @patch(
        "loom.workflows.scene_activities"
        ".ingest_workflow_duration"
    )
    @patch(
        "loom.workflows.scene_activities"
        ".get_db_session"
    )
    async def test_detect_scenes_observes_metric_non_video(
        self,
        mock_session_ctx: MagicMock,
        mock_metric: MagicMock,
    ) -> None:
        from loom.workflows.scene_activities import (
            detect_asset_scenes,
        )

        asset = _make_asset(media_type="image")
        ctx, _ = _mock_session(asset)
        mock_session_ctx.return_value = ctx

        result = await detect_asset_scenes(_ASSET_ID)

        assert result == []
        mock_metric.labels.assert_called_with(
            activity="scene_detect"
        )
        mock_metric.labels.return_value.observe.assert_called_once()
        duration = (
            mock_metric.labels.return_value.observe.call_args[0][0]
        )
        assert duration > 0


class TestTranscriptionActivityMetrics:
    """verify transcription activities observe the histogram."""

    @patch(
        "loom.workflows.transcription_activities"
        ".ingest_workflow_duration"
    )
    @patch(
        "loom.workflows.transcription_activities"
        ".transcribe_audio"
    )
    async def test_transcribe_observes_metric(
        self,
        mock_transcribe: MagicMock,
        mock_metric: MagicMock,
    ) -> None:
        from loom.workflows.transcription_activities import (
            transcribe_asset,
        )

        mock_transcribe.return_value = [
            {"start": 0, "end": 1, "text": "hello"}
        ]

        result = await transcribe_asset(
            _ASSET_ID, "/tmp/audio.wav"  # noqa: S108
        )

        assert len(result) == 1
        mock_metric.labels.assert_called_with(
            activity="transcribe"
        )
        mock_metric.labels.return_value.observe.assert_called_once()
        duration = (
            mock_metric.labels.return_value.observe.call_args[0][0]
        )
        assert duration > 0

    @patch(
        "loom.workflows.transcription_activities"
        ".ingest_workflow_duration"
    )
    @patch(
        "loom.workflows.transcription_activities"
        ".diarize_audio"
    )
    async def test_diarize_observes_metric(
        self,
        mock_diarize: MagicMock,
        mock_metric: MagicMock,
    ) -> None:
        from loom.workflows.transcription_activities import (
            diarize_asset,
        )

        mock_diarize.return_value = []

        result = await diarize_asset(
            _ASSET_ID, "/tmp/audio.wav"  # noqa: S108
        )

        assert result == []
        mock_metric.labels.assert_called_with(
            activity="diarize"
        )
        mock_metric.labels.return_value.observe.assert_called_once()
        duration = (
            mock_metric.labels.return_value.observe.call_args[0][0]
        )
        assert duration > 0


class TestMetricsModuleGracefulDegradation:
    """verify metrics module works without prometheus_client."""

    def test_noop_histogram_accepts_labels_and_observe(
        self,
    ) -> None:
        from loom.metrics import _NoOpHistogram

        h = _NoOpHistogram()
        h.labels(activity="test").observe(1.23)
