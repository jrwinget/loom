from unittest.mock import MagicMock, patch

import httpx
import pytest_asyncio

from loom.config import Settings, get_settings
from loom.dependencies import get_db_session


class MockSession:
    async def execute(self, stmt):
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        return result

    def add(self, obj: object) -> None:
        pass

    async def commit(self) -> None:
        pass


@pytest_asyncio.fixture
def mock_settings():
    return Settings(
        secret_key=("test-secret-key-that-is-long-enough-for-validation"),
        database_url="sqlite+aiosqlite:///",
    )


def _create_app(settings: Settings, *, with_db: bool = False) -> object:
    get_settings.cache_clear()
    with patch("loom.config.get_settings", return_value=settings):
        from loom.main import create_app

        app = create_app()

    if with_db:

        async def override_db():
            yield MockSession()

        app.dependency_overrides[get_db_session] = override_db
        app.state.db_session_factory = None

    return app


async def test_csrf_valid_token_passes(
    mock_settings: Settings,
) -> None:
    """matching csrf cookie and header should pass."""
    app = _create_app(mock_settings)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as ac:
        resp = await ac.post(
            "/api/v1/health",
            cookies={"csrf_token": "abc123"},
            headers={"X-CSRF-Token": "abc123"},
        )
        # health endpoint exists; csrf should not block
        assert resp.status_code != 403


async def test_csrf_missing_header_fails(
    mock_settings: Settings,
) -> None:
    """csrf cookie present but header missing returns 403."""
    app = _create_app(mock_settings)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as ac:
        resp = await ac.post(
            "/api/v1/cases",
            cookies={"csrf_token": "abc123"},
            json={"name": "test"},
        )
        assert resp.status_code == 403
        assert "CSRF" in resp.json()["detail"]


async def test_csrf_mismatched_token_fails(
    mock_settings: Settings,
) -> None:
    """different cookie and header values returns 403."""
    app = _create_app(mock_settings)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as ac:
        resp = await ac.post(
            "/api/v1/cases",
            cookies={"csrf_token": "abc123"},
            headers={"X-CSRF-Token": "wrong"},
            json={"name": "test"},
        )
        assert resp.status_code == 403


async def test_csrf_exempt_login_passes(
    mock_settings: Settings,
) -> None:
    """login endpoint is exempt from csrf checks."""
    app = _create_app(mock_settings, with_db=True)

    with patch(
        "loom.security.auth.get_settings",
        return_value=mock_settings,
    ):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            resp = await ac.post(
                "/api/v1/auth/login",
                cookies={"csrf_token": "abc123"},
                json={
                    "email": "nobody@example.com",
                    "password": "test",
                },
            )
            # should get 401 (bad creds), not 403 (csrf)
            assert resp.status_code == 401


async def test_csrf_no_cookie_passes(
    mock_settings: Settings,
) -> None:
    """requests without csrf cookie are not checked."""
    app = _create_app(mock_settings)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as ac:
        resp = await ac.post(
            "/api/v1/cases",
            json={"name": "test"},
        )
        # should get 401 (no auth), not 403 (csrf)
        assert resp.status_code != 403


async def test_csrf_get_requests_skip_check(
    mock_settings: Settings,
) -> None:
    """GET requests should not be subject to csrf."""
    app = _create_app(mock_settings)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as ac:
        resp = await ac.get(
            "/api/v1/health",
            cookies={"csrf_token": "abc123"},
        )
        assert resp.status_code != 403
