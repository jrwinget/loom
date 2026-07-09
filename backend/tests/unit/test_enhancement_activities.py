"""tests for the enhancement activity.

the ffmpeg-calling service functions and storage are mocked; the
activity's own job is to load the asset, wire the service to storage,
and record a derivative with full provenance.
"""

import inspect
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest

from loom.models.derivative import Derivative
from loom.services.engines import EngineUnavailableError
from loom.services.enhancement import MODEL_NAME
from loom.workflows.enhancement_activities import enhance_asset

_ASSET_ID = "01912345-6789-7abc-8def-0123456789ab"


def _make_asset() -> MagicMock:
    asset = MagicMock()
    asset.id = UUID(_ASSET_ID)
    asset.media_type = "video"
    asset.original_filename = "clip.mp4"
    asset.storage_key = "case/asset/original.mp4"
    asset.mime_type = "video/mp4"
    return asset


def _session_with_asset(asset: MagicMock) -> AsyncMock:
    session = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = asset
    session.execute.return_value = result
    session.add = MagicMock()
    return session


def _patch_env(
    session: AsyncMock,
    storage: MagicMock,
    tmp_path: Path,
) -> list[object]:
    """patch the module's session/storage/temp-dir seams."""
    ctx = AsyncMock()
    ctx.__aenter__.return_value = session
    return [
        patch(
            "loom.workflows.enhancement_activities.get_db_session",
            return_value=ctx,
        ),
        patch(
            "loom.workflows.enhancement_activities.get_storage_backend",
            return_value=storage,
        ),
        patch(
            "loom.workflows.enhancement_activities.upload_tmp_dir",
            return_value=tmp_path,
        ),
    ]


class TestEnhanceAssetActivity:
    def test_is_temporal_activity(self) -> None:
        assert hasattr(enhance_asset, "__temporal_activity_definition")

    def test_is_async(self) -> None:
        assert inspect.iscoroutinefunction(enhance_asset)

    async def test_records_derivative_with_provenance(
        self,
        tmp_path: Path,
    ) -> None:
        asset = _make_asset()
        session = _session_with_asset(asset)
        storage = MagicMock()

        def fake_enhance(src: str, out: str, params: object) -> None:
            # a real derivative file so hashing and sizing succeed
            Path(out).write_bytes(b"enhanced-bytes")

        seams = _patch_env(session, storage, tmp_path)
        with (
            seams[0],
            seams[1],
            seams[2],
            patch(
                "loom.workflows.enhancement_activities.enhance_video",
                side_effect=fake_enhance,
            ),
        ):
            result = await enhance_asset(
                _ASSET_ID, json.dumps({"brightness": 0.2})
            )

        deriv = session.add.call_args.args[0]
        assert isinstance(deriv, Derivative)
        assert deriv.type == "enhancement"
        assert deriv.storage_key.startswith(f"enhancements/{_ASSET_ID}/")
        assert result == str(deriv.id)
        # provenance maps 1:1 onto the frontend WhyPopover props
        provenance = deriv.generation_params
        assert provenance["model_name"] == MODEL_NAME
        assert provenance["model_params"]["filter_chain"] == "eq=brightness=0.2"
        storage.upload_file_move.assert_called_once()
        session.commit.assert_awaited_once()

    async def test_engine_unavailable_propagates(
        self,
        tmp_path: Path,
    ) -> None:
        asset = _make_asset()
        session = _session_with_asset(asset)
        storage = MagicMock()

        def boom(src: str, out: str, params: object) -> None:
            raise EngineUnavailableError("media_pipeline", "install ffmpeg")

        seams = _patch_env(session, storage, tmp_path)
        with (
            seams[0],
            seams[1],
            seams[2],
            patch(
                "loom.workflows.enhancement_activities.enhance_video",
                side_effect=boom,
            ),
            pytest.raises(EngineUnavailableError),
        ):
            await enhance_asset(_ASSET_ID, json.dumps({}))

        # no fabricated output: nothing recorded, nothing uploaded
        session.add.assert_not_called()
        storage.upload_file_move.assert_not_called()
