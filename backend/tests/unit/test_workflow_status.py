"""tests for workflow status polling endpoint."""

from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from loom.api.v1.workflows import (
    WorkflowStatusResponse,
    router,
)

_CASE_ID = "01912345-6789-7abc-8def-0123456789ef"
_WORKFLOW_ID = "ingest-01912345-6789-7abc-8def-0123456789ab"


class TestWorkflowStatusResponse:
    """schema validation for WorkflowStatusResponse."""

    def test_minimal_response(self) -> None:
        resp = WorkflowStatusResponse(
            workflow_id=_WORKFLOW_ID,
            status="running",
        )
        assert resp.workflow_id == _WORKFLOW_ID
        assert resp.status == "running"
        assert resp.start_time is None
        assert resp.close_time is None
        assert resp.error is None

    def test_full_response(self) -> None:
        now = datetime.now(tz=UTC)
        resp = WorkflowStatusResponse(
            workflow_id=_WORKFLOW_ID,
            status="completed",
            start_time=now,
            close_time=now,
            error=None,
        )
        assert resp.status == "completed"
        assert resp.start_time == now

    def test_failed_with_error(self) -> None:
        resp = WorkflowStatusResponse(
            workflow_id=_WORKFLOW_ID,
            status="failed",
            error="activity timeout",
        )
        assert resp.status == "failed"
        assert resp.error == "activity timeout"


class TestWorkflowStatusEndpoint:
    """integration tests for the workflow status endpoint."""

    @pytest.fixture
    def app(self) -> FastAPI:
        """create a minimal app with the workflows router."""
        application = FastAPI()
        application.include_router(router, prefix="/api/v1")
        return application

    async def test_requires_authentication(self, app: FastAPI) -> None:
        """returns 401 without auth token."""
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            resp = await client.get(
                f"/api/v1/cases/{_CASE_ID}/workflows/{_WORKFLOW_ID}/status"
            )
            assert resp.status_code == 401
