from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import httpx
import pytest_asyncio

from loom.config import Settings, get_settings
from loom.dependencies import get_db_session
from loom.models.transcript import TranscriptSegment
from loom.security.auth import create_access_token

# fixed uuids for test entities
_ADMIN_ID = UUID("01912345-6789-7abc-8def-0123456789ab")
_CASE_ID = UUID("01912345-6789-7abc-8def-0123456789ef")
_ASSET_ID = UUID("01912345-6789-7abc-8def-012345678903")
_SEGMENT_ID = UUID("01912345-6789-7abc-8def-012345678910")

_NOW = datetime(2025, 1, 1, tzinfo=UTC)

# module path prefix for patching
_SVC_TR = "loom.api.v1.transcripts"
_SVC_CASE = f"{_SVC_TR}.check_case_access"


class _StubSession:
    """minimal stub session for dependency override."""

    async def execute(self, stmt):
        return MagicMock()

    def add(self, obj):
        pass

    async def flush(self) -> None:
        pass

    async def commit(self) -> None:
        pass

    async def refresh(self, obj):
        pass


def _create_app(settings: Settings) -> object:
    """build a test app with stub db session."""
    get_settings.cache_clear()

    with patch(
        "loom.config.get_settings",
        return_value=settings,
    ):
        from loom.main import create_app

        application = create_app()

    async def override_db():
        yield _StubSession()

    application.dependency_overrides[get_db_session] = override_db
    # prevent audit middleware from writing to db
    application.state.db_session_factory = None

    return application


def _make_segment(
    *,
    speaker_label: str | None = None,
    start_time: float = 0.0,
    end_time: float = 5.0,
    text: str = "test segment",
) -> MagicMock:
    """build a mock transcript segment."""
    seg = MagicMock(spec=TranscriptSegment)
    seg.id = _SEGMENT_ID
    seg.asset_id = _ASSET_ID
    seg.speaker_label = speaker_label
    seg.start_time = start_time
    seg.end_time = end_time
    seg.text = text
    seg.confidence = 0.95
    seg.language = "en"
    seg.created_at = _NOW
    return seg


@pytest_asyncio.fixture
def mock_settings():
    """override settings for tests."""
    return Settings(
        secret_key="test-secret-key-that-is-long-enough-for-validation",
        access_token_expire_minutes=15,
        refresh_token_expire_days=7,
        database_url="sqlite+aiosqlite:///",
    )


def _auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def test_get_transcript_empty(
    mock_settings: Settings,
) -> None:
    """get transcript returns empty for no segments."""
    app = _create_app(mock_settings)

    with (
        patch(
            "loom.security.auth.get_settings",
            return_value=mock_settings,
        ),
        patch(
            _SVC_CASE,
            new_callable=AsyncMock,
            return_value=True,
        ),
        patch(
            f"{_SVC_TR}.get_transcript_segments",
            new_callable=AsyncMock,
            return_value=[],
        ),
    ):
        token = create_access_token(str(_ADMIN_ID), "admin")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            resp = await ac.get(
                f"/api/v1/cases/{_CASE_ID}/assets/{_ASSET_ID}/transcript",
                headers=_auth_header(token),
            )

    assert resp.status_code == 200
    data = resp.json()
    assert data["segments"] == []
    assert data["total_duration"] == 0.0
    assert data["speaker_count"] == 0


async def test_start_transcription_returns_202(
    mock_settings: Settings,
) -> None:
    """post transcribe returns 202."""
    app = _create_app(mock_settings)

    with (
        patch(
            "loom.security.auth.get_settings",
            return_value=mock_settings,
        ),
        patch(
            _SVC_CASE,
            new_callable=AsyncMock,
            return_value=True,
        ),
    ):
        token = create_access_token(str(_ADMIN_ID), "admin")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            resp = await ac.post(
                f"/api/v1/cases/{_CASE_ID}/assets/{_ASSET_ID}/transcribe",
                headers=_auth_header(token),
            )

    assert resp.status_code == 202
    data = resp.json()
    assert data["asset_id"] == str(_ASSET_ID)
    assert data["status"] == "accepted"


async def test_get_transcript_with_speaker_filter(
    mock_settings: Settings,
) -> None:
    """get transcript filters by speaker label."""
    app = _create_app(mock_settings)
    seg = _make_segment(speaker_label="SPEAKER_0")

    with (
        patch(
            "loom.security.auth.get_settings",
            return_value=mock_settings,
        ),
        patch(
            _SVC_CASE,
            new_callable=AsyncMock,
            return_value=True,
        ),
        patch(
            f"{_SVC_TR}.get_transcript_segments",
            new_callable=AsyncMock,
            return_value=[seg],
        ) as mock_get,
    ):
        token = create_access_token(str(_ADMIN_ID), "admin")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            resp = await ac.get(
                f"/api/v1/cases/{_CASE_ID}/assets/{_ASSET_ID}/transcript",
                params={"speaker": "SPEAKER_0"},
                headers=_auth_header(token),
            )

    assert resp.status_code == 200
    data = resp.json()
    assert len(data["segments"]) == 1
    assert data["speaker_count"] == 1
    # verify speaker filter was passed through
    mock_get.assert_called_once()
    call_kwargs = mock_get.call_args
    assert call_kwargs.kwargs["speaker"] == "SPEAKER_0"


async def test_viewer_cannot_start_transcription(
    mock_settings: Settings,
) -> None:
    """viewer cannot start transcription (403)."""
    app = _create_app(mock_settings)

    with (
        patch(
            "loom.security.auth.get_settings",
            return_value=mock_settings,
        ),
        patch(
            _SVC_CASE,
            new_callable=AsyncMock,
            return_value=False,
        ),
    ):
        token = create_access_token(str(_ADMIN_ID), "analyst")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            resp = await ac.post(
                f"/api/v1/cases/{_CASE_ID}/assets/{_ASSET_ID}/transcribe",
                headers=_auth_header(token),
            )

    assert resp.status_code == 403
