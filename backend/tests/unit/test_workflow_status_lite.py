"""unit tests for lite workflow-status derivation.

the lite profile reports in-process status when known, and falls
back to deriving status from the rows a workflow produced (after a
restart drops the in-memory map).
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from loom.api.v1 import workflows as wf

_ASSET = str(uuid4())


def _db_with_asset(processing_status: str | None) -> AsyncMock:
    db = AsyncMock()
    if processing_status is None:
        db.get = AsyncMock(return_value=None)
    else:
        asset = MagicMock()
        asset.processing_status = processing_status
        db.get = AsyncMock(return_value=asset)
    return db


async def test_derive_ingest_complete() -> None:
    db = _db_with_asset("complete")
    assert await wf._derive_status_from_db(db, f"ingest-{_ASSET}") == (
        "completed"
    )


async def test_derive_url_ingest_processing_is_running() -> None:
    db = _db_with_asset("processing")
    status = await wf._derive_status_from_db(db, f"url-ingest-{_ASSET}")
    assert status == "running"


async def test_derive_ingest_missing_asset_is_none() -> None:
    db = _db_with_asset(None)
    assert await wf._derive_status_from_db(db, f"ingest-{_ASSET}") is None


async def test_derive_export_status_mapping() -> None:
    db = AsyncMock()
    export = MagicMock()
    export.status = "failed"
    db.get = AsyncMock(return_value=export)
    assert await wf._derive_status_from_db(db, "export-abc") == "failed"


async def test_derive_rows_present_is_completed() -> None:
    db = AsyncMock()
    db.scalar = AsyncMock(return_value=3)
    assert await wf._derive_status_from_db(db, f"ocr-{_ASSET}") == "completed"


async def test_derive_rows_absent_is_running() -> None:
    db = AsyncMock()
    db.scalar = AsyncMock(return_value=0)
    status = await wf._derive_status_from_db(db, f"scene-detect-{_ASSET}")
    assert status == "running"


async def test_derive_unknown_prefix_is_none() -> None:
    db = AsyncMock()
    assert await wf._derive_status_from_db(db, "mystery-123") is None


async def test_lite_status_prefers_in_memory() -> None:
    db = AsyncMock()
    with patch.object(wf, "lite_workflow_status", return_value="failed"):
        resp = await wf._lite_status(db, f"ingest-{_ASSET}")
    assert resp.status == "failed"
    db.get.assert_not_called()


async def test_lite_status_falls_back_to_db() -> None:
    db = _db_with_asset("complete")
    with patch.object(wf, "lite_workflow_status", return_value=None):
        resp = await wf._lite_status(db, f"ingest-{_ASSET}")
    assert resp.status == "completed"


async def test_lite_status_unknown_is_404() -> None:
    db = AsyncMock()
    with (
        patch.object(wf, "lite_workflow_status", return_value=None),
        pytest.raises(HTTPException) as exc,
    ):
        await wf._lite_status(db, "mystery-123")
    assert exc.value.status_code == 404
