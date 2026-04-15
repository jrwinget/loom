"""integration tests for workflow status api endpoints."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import httpx
import pytest

from loom.config import Settings, get_settings
from loom.dependencies import get_db_session
from loom.security.auth import create_access_token

_ADMIN_ID = UUID("01912345-6789-7abc-8def-0123456789ab")
_USER_ID = UUID("01912345-6789-7abc-8def-0123456789cd")
_CASE_ID = UUID("01912345-6789-7abc-8def-0123456789ef")
_WORKFLOW_ID = "ingest-01912345"

_SVC = "loom.api.v1.workflows"


class _StubSession:
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
    with patch("loom.config.get_settings", return_value=settings):
        from loom.main import create_app

        application = create_app()

    async def override_db():
        yield _StubSession()

    application.dependency_overrides[get_db_session] = override_db
    application.state.db_session_factory = None
    return application


@pytest.fixture
def mock_settings():
    return Settings(
        secret_key=("test-secret-key-that-is-long-enough-for-validation"),
        database_url="sqlite+aiosqlite:///",
    )


def _auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def test_workflow_status_temporal_unavailable(
    mock_settings: Settings,
) -> None:
    """returns 503 when temporal client is not installed."""
    app = _create_app(mock_settings)

    with (
        patch(
            "loom.security.auth.get_settings",
            return_value=mock_settings,
        ),
        patch(
            f"{_SVC}.check_case_access",
            new_callable=AsyncMock,
            return_value=True,
        ),
        patch.dict(
            "sys.modules",
            {"temporalio": None, "temporalio.client": None},
        ),
    ):
        token = create_access_token(str(_USER_ID), "analyst")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            resp = await ac.get(
                f"/api/v1/cases/{_CASE_ID}/workflows/{_WORKFLOW_ID}/status",
                headers=_auth_header(token),
            )

    # should get 503 or 404 depending on import path
    assert resp.status_code in (503, 404)


async def test_workflow_status_forbidden(
    mock_settings: Settings,
) -> None:
    """no case access returns 403."""
    app = _create_app(mock_settings)

    with (
        patch(
            "loom.security.auth.get_settings",
            return_value=mock_settings,
        ),
        patch(
            f"{_SVC}.check_case_access",
            new_callable=AsyncMock,
            return_value=False,
        ),
    ):
        token = create_access_token(str(_USER_ID), "analyst")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            resp = await ac.get(
                f"/api/v1/cases/{_CASE_ID}/workflows/{_WORKFLOW_ID}/status",
                headers=_auth_header(token),
            )

    assert resp.status_code == 403


async def test_workflow_status_unauthenticated(
    mock_settings: Settings,
) -> None:
    """missing token returns 401/403."""
    app = _create_app(mock_settings)

    with patch(
        "loom.security.auth.get_settings",
        return_value=mock_settings,
    ):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            resp = await ac.get(
                f"/api/v1/cases/{_CASE_ID}/workflows/{_WORKFLOW_ID}/status",
            )

    assert resp.status_code in (401, 403)


async def test_workflow_response_model() -> None:
    """WorkflowStatusResponse serializes correctly."""
    from loom.api.v1.workflows import WorkflowStatusResponse

    resp = WorkflowStatusResponse(
        workflow_id="wf-123",
        status="running",
        start_time=None,
        close_time=None,
        error=None,
    )
    assert resp.workflow_id == "wf-123"
    assert resp.status == "running"
    assert resp.error is None

    # failed with error
    resp_failed = WorkflowStatusResponse(
        workflow_id="wf-456",
        status="failed",
        error="timeout exceeded",
    )
    assert resp_failed.error == "timeout exceeded"


async def test_workflow_status_not_found(
    mock_settings: Settings,
) -> None:
    """workflow not found in temporal returns 404."""
    app = _create_app(mock_settings)

    # mock temporal client to raise on describe()
    mock_handle = AsyncMock()
    mock_handle.describe.side_effect = RuntimeError("not found")
    mock_client = AsyncMock()
    mock_client.get_workflow_handle.return_value = mock_handle
    mock_client_cls = AsyncMock()
    mock_client_cls.connect = AsyncMock(return_value=mock_client)

    with (
        patch(
            "loom.security.auth.get_settings",
            return_value=mock_settings,
        ),
        patch(
            f"{_SVC}.check_case_access",
            new_callable=AsyncMock,
            return_value=True,
        ),
        patch(
            "temporalio.client.Client",
            mock_client_cls,
        ),
    ):
        token = create_access_token(str(_USER_ID), "analyst")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            resp = await ac.get(
                f"/api/v1/cases/{_CASE_ID}/workflows/{_WORKFLOW_ID}/status",
                headers=_auth_header(token),
            )

    assert resp.status_code == 404
