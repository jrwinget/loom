"""tests that workflow-start endpoints propagate failures as 502."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from loom.api.v1.exports import router as exports_router
from loom.api.v1.ocr import router as ocr_router
from loom.api.v1.scenes import router as scenes_router
from loom.api.v1.transcripts import router as transcripts_router
from loom.dependencies import get_db_session
from loom.security.rbac import require_authenticated

_CASE_ID = str(uuid4())
_ASSET_ID = str(uuid4())
_USER_ID = str(uuid4())
_TOKEN_PAYLOAD = {"sub": _USER_ID, "role": "admin"}


def _fake_auth() -> dict:
    return _TOKEN_PAYLOAD


def _fake_db() -> AsyncMock:
    return AsyncMock()


def _build_app(*routers) -> FastAPI:  # type: ignore[no-untyped-def]
    application = FastAPI()
    for r in routers:
        application.include_router(r, prefix="/api/v1")
    application.dependency_overrides[require_authenticated] = _fake_auth
    application.dependency_overrides[get_db_session] = _fake_db
    return application


def _patch_case_access(  # type: ignore[no-untyped-def]
    module: str,
    allowed: bool = True,
):
    return patch(
        f"loom.api.v1.{module}.check_case_access",
        new_callable=AsyncMock,
        return_value=allowed,
    )


def _patch_temporal_connect(  # type: ignore[no-untyped-def]
    *,
    fail: bool = False,
):
    mock_client = AsyncMock()
    mock_client.start_workflow = AsyncMock()
    if fail:
        mock_connect = AsyncMock(
            side_effect=RuntimeError("temporal down"),
        )
    else:
        mock_connect = AsyncMock(return_value=mock_client)
    return patch(
        "temporalio.client.Client.connect",
        mock_connect,
    )


class TestOcrWorkflowEndpoint:
    """POST /ocr/run returns 502 on temporal failure."""

    url = f"/api/v1/cases/{_CASE_ID}/assets/{_ASSET_ID}/ocr/run"

    @pytest.mark.asyncio
    async def test_happy_path_returns_202(self) -> None:
        app = _build_app(ocr_router)
        with (
            _patch_case_access("ocr"),
            _patch_temporal_connect(fail=False),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                resp = await client.post(self.url)
        assert resp.status_code == 202
        body = resp.json()
        assert body["workflow_id"] == f"ocr-{_ASSET_ID}"

    @pytest.mark.asyncio
    async def test_temporal_failure_returns_502(self) -> None:
        app = _build_app(ocr_router)
        with (
            _patch_case_access("ocr"),
            _patch_temporal_connect(fail=True),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                resp = await client.post(self.url)
        assert resp.status_code == 502
        assert resp.json()["detail"] == ("workflow service unavailable")


class TestSceneDetectionEndpoint:
    """POST /scenes/detect returns 502 on temporal failure."""

    url = f"/api/v1/cases/{_CASE_ID}/assets/{_ASSET_ID}/scenes/detect"

    @pytest.mark.asyncio
    async def test_happy_path_returns_202(self) -> None:
        app = _build_app(scenes_router)
        with (
            _patch_case_access("scenes"),
            _patch_temporal_connect(fail=False),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                resp = await client.post(self.url)
        assert resp.status_code == 202
        body = resp.json()
        assert body["workflow_id"] == (f"scene-detect-{_ASSET_ID}")

    @pytest.mark.asyncio
    async def test_temporal_failure_returns_502(self) -> None:
        app = _build_app(scenes_router)
        with (
            _patch_case_access("scenes"),
            _patch_temporal_connect(fail=True),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                resp = await client.post(self.url)
        assert resp.status_code == 502
        assert resp.json()["detail"] == ("workflow service unavailable")


class TestTranscriptionEndpoint:
    """POST /transcribe returns 502 on temporal failure."""

    url = f"/api/v1/cases/{_CASE_ID}/assets/{_ASSET_ID}/transcribe"

    @pytest.mark.asyncio
    async def test_happy_path_returns_202(self) -> None:
        app = _build_app(transcripts_router)
        with (
            _patch_case_access("transcripts"),
            _patch_temporal_connect(fail=False),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                resp = await client.post(self.url)
        assert resp.status_code == 202
        body = resp.json()
        assert body["workflow_id"] == (f"transcribe-{_ASSET_ID}")

    @pytest.mark.asyncio
    async def test_temporal_failure_returns_502(self) -> None:
        app = _build_app(transcripts_router)
        with (
            _patch_case_access("transcripts"),
            _patch_temporal_connect(fail=True),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                resp = await client.post(self.url)
        assert resp.status_code == 502
        assert resp.json()["detail"] == ("workflow service unavailable")


class TestExportEndpoint:
    """POST /exports returns 502 on temporal failure."""

    url = f"/api/v1/cases/{_CASE_ID}/exports"

    def _patch_create_export(self) -> patch:  # type: ignore[type-arg]
        mock_export = MagicMock()
        mock_export.id = uuid4()
        mock_export.case_id = _CASE_ID
        mock_export.name = "test"
        mock_export.format = "zip"
        mock_export.status = "pending"
        mock_export.storage_key = ""
        mock_export.sha256_hash = ""
        mock_export.created_by = _USER_ID
        mock_export.created_at = datetime.now(tz=UTC)
        mock_export.updated_at = datetime.now(tz=UTC)
        mock_export.manifest = None
        return patch(
            "loom.api.v1.exports.create_export_record",
            new_callable=AsyncMock,
            return_value=mock_export,
        )

    @pytest.mark.asyncio
    async def test_happy_path_returns_201(self) -> None:
        app = _build_app(exports_router)
        with (
            _patch_case_access("exports"),
            self._patch_create_export(),
            _patch_temporal_connect(fail=False),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                resp = await client.post(
                    self.url,
                    json={
                        "name": "test export",
                        "format": "zip",
                    },
                )
        assert resp.status_code == 201

    @pytest.mark.asyncio
    async def test_temporal_failure_returns_502(self) -> None:
        app = _build_app(exports_router)
        with (
            _patch_case_access("exports"),
            self._patch_create_export(),
            _patch_temporal_connect(fail=True),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                resp = await client.post(
                    self.url,
                    json={
                        "name": "test export",
                        "format": "zip",
                    },
                )
        assert resp.status_code == 502
        assert resp.json()["detail"] == ("workflow service unavailable")
