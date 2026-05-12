"""API-level tests for correlation endpoints.

Focus: input validation on the list filter and HTTP-status mapping
for service-level ``ValueError``s raised during decide.
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import httpx
import pytest_asyncio

from loom.config import Settings, get_settings
from loom.dependencies import get_db_session
from loom.models.correlation import CorrelationCandidate
from loom.security.auth import create_access_token

_ADMIN_ID = UUID("01912345-6789-7abc-8def-0123456789ab")
_CASE_ID = UUID("01912345-6789-7abc-8def-0123456789ef")
_CANDIDATE_ID = UUID("01912345-6789-7abc-8def-012345678900")
_NOW = datetime(2025, 1, 1, tzinfo=UTC)

_SVC = "loom.api.v1.correlations"
_CASE_ACCESS = f"{_SVC}.check_case_access"


class _StubSession:
    """minimal stub async session for dependency override."""

    async def execute(self, stmt):
        return MagicMock()

    def add(self, obj):
        pass

    async def flush(self):
        pass

    async def commit(self):
        pass

    async def refresh(self, obj):
        pass


def _create_app(settings: Settings) -> object:
    get_settings.cache_clear()
    with patch(
        "loom.config.get_settings",
        return_value=settings,
    ):
        from loom.main import create_app

        application = create_app()

    async def _override_db():
        yield _StubSession()

    application.dependency_overrides[get_db_session] = _override_db
    # skip audit middleware db writes
    application.state.db_session_factory = None
    return application


@pytest_asyncio.fixture
def mock_settings() -> Settings:
    return Settings(
        secret_key="test-secret-key-that-is-long-enough-for-validation",
        access_token_expire_minutes=15,
        refresh_token_expire_days=7,
        database_url="sqlite+aiosqlite:///",
    )


def _auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _make_candidate(
    *,
    status_value: str = "pending",
) -> MagicMock:
    row = MagicMock(spec=CorrelationCandidate)
    row.id = _CANDIDATE_ID
    row.case_id = _CASE_ID
    row.start_utc = _NOW
    row.end_utc = _NOW
    row.confidence = 0.75
    row.reasoning = {}
    row.status = status_value
    row.decided_by = None
    row.decided_at = None
    row.created_at = _NOW
    return row


async def test_list_rejects_invalid_status(
    mock_settings: Settings,
) -> None:
    """An arbitrary status value is rejected by FastAPI with 422."""
    app = _create_app(mock_settings)

    with (
        patch(
            "loom.security.auth.get_settings",
            return_value=mock_settings,
        ),
        patch(
            _CASE_ACCESS,
            new_callable=AsyncMock,
            return_value=True,
        ),
    ):
        token = create_access_token(str(_ADMIN_ID), "admin")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            resp = await ac.get(
                f"/api/v1/cases/{_CASE_ID}/correlations",
                params={"status": "bogus"},
                headers=_auth_header(token),
            )

    assert resp.status_code == 422


async def test_decide_already_decided_returns_409(
    mock_settings: Settings,
) -> None:
    """Re-deciding a terminal candidate yields 409, not 500."""
    app = _create_app(mock_settings)
    existing = _make_candidate(status_value="accepted")

    # first scalar_one_or_none returns the accepted candidate so the
    # case-belongs check passes; decide_candidate then raises.
    async def _override_db():
        stub = _StubSession()
        result = MagicMock()
        result.scalar_one_or_none.return_value = existing
        stub.execute = AsyncMock(return_value=result)
        yield stub

    app.dependency_overrides[get_db_session] = _override_db

    with (
        patch(
            "loom.security.auth.get_settings",
            return_value=mock_settings,
        ),
        patch(
            _CASE_ACCESS,
            new_callable=AsyncMock,
            return_value=True,
        ),
        patch(
            f"{_SVC}.decide_candidate",
            new_callable=AsyncMock,
            side_effect=ValueError(
                f"candidate {_CANDIDATE_ID} already decided "
                "(accepted); cannot change to rejected"
            ),
        ),
    ):
        token = create_access_token(str(_ADMIN_ID), "admin")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            resp = await ac.post(
                f"/api/v1/cases/{_CASE_ID}/correlations/{_CANDIDATE_ID}/decide",
                json={"status": "rejected"},
                headers=_auth_header(token),
            )

    assert resp.status_code == 409
    body = resp.json()
    assert "already decided" in body["detail"]
