"""shared fixtures for temporal workflow e2e tests.

provides a session-scoped time-skipping ``WorkflowEnvironment``
so each test can register a Worker against an in-process server
without paying the ~5s java-less startup per test. activity retry
intervals are skipped automatically, keeping suite runtime sane.
"""

from collections.abc import AsyncIterator

import pytest_asyncio
from temporalio.client import Client
from temporalio.testing import WorkflowEnvironment


@pytest_asyncio.fixture(scope="session")
async def workflow_env() -> AsyncIterator[WorkflowEnvironment]:
    """yield a time-skipping temporal env for the test session.

    time-skipping is the right default: ingest/correlation use
    minute-scale activity timeouts that would otherwise stall the
    suite. the env starts an in-process server bundled with the
    sdk, so no docker or external temporal is required.
    """
    env = await WorkflowEnvironment.start_time_skipping()
    try:
        yield env
    finally:
        await env.shutdown()


@pytest_asyncio.fixture
async def temporal_client(
    workflow_env: WorkflowEnvironment,
) -> Client:
    """return a client wired to the session-scoped test env."""
    return workflow_env.client
