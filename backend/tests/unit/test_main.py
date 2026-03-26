"""tests for main app factory."""

from unittest.mock import patch

from fastapi import FastAPI

from loom.config import Settings, get_settings
from loom.main import create_app


def _make_settings(**overrides: object) -> Settings:
    """create test settings."""
    defaults = {
        "secret_key": ("test-secret-key-that-is-long-enough-for-validation"),
        "debug": False,
        "log_level": "info",
    }
    defaults.update(overrides)
    return Settings(**defaults)  # type: ignore[arg-type]


class TestCreateApp:
    """create_app returns FastAPI instance."""

    def test_returns_fastapi_instance(self) -> None:
        """factory produces a FastAPI app."""
        get_settings.cache_clear()
        with patch(
            "loom.main.get_settings",
            return_value=_make_settings(),
        ):
            app = create_app()
        assert isinstance(app, FastAPI)

    def test_app_has_title(self) -> None:
        """app title is Loom."""
        get_settings.cache_clear()
        with patch(
            "loom.main.get_settings",
            return_value=_make_settings(),
        ):
            app = create_app()
        assert app.title == "Loom"

    def test_app_version(self) -> None:
        """app version is set."""
        get_settings.cache_clear()
        with patch(
            "loom.main.get_settings",
            return_value=_make_settings(),
        ):
            app = create_app()
        assert app.version == "0.1.0"


class TestCors:
    """CORS configuration based on debug flag."""

    def test_debug_allows_all_origins(self) -> None:
        """debug=True configures CORS with wildcard origins."""
        get_settings.cache_clear()
        with patch(
            "loom.main.get_settings",
            return_value=_make_settings(debug=True),
        ):
            app = create_app()

        # check user_middleware includes CORSMiddleware
        from starlette.middleware.cors import CORSMiddleware

        cors_entries = [
            m for m in app.user_middleware if m.cls is CORSMiddleware
        ]
        assert len(cors_entries) == 1
        assert "*" in cors_entries[0].kwargs["allow_origins"]

    def test_production_no_origins(self) -> None:
        """debug=False configures CORS with empty origins."""
        get_settings.cache_clear()
        with patch(
            "loom.main.get_settings",
            return_value=_make_settings(debug=False),
        ):
            app = create_app()

        from starlette.middleware.cors import CORSMiddleware

        cors_entries = [
            m for m in app.user_middleware if m.cls is CORSMiddleware
        ]
        assert len(cors_entries) == 1
        assert cors_entries[0].kwargs["allow_origins"] == []


class TestRequestIdMiddleware:
    """X-Request-Id header added to responses."""

    async def test_response_has_request_id(self) -> None:
        """every response gets an X-Request-Id header."""
        import httpx

        get_settings.cache_clear()
        with patch(
            "loom.main.get_settings",
            return_value=_make_settings(debug=True),
        ):
            app = create_app()

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            resp = await client.get("/api/v1/health")

        assert "X-Request-Id" in resp.headers
        # should be a uuid-like string
        rid = resp.headers["X-Request-Id"]
        assert len(rid) == 36  # uuid format


class TestRouterIncluded:
    """api router is mounted at /api/v1."""

    def test_api_routes_exist(self) -> None:
        """app has routes under /api/v1/."""
        get_settings.cache_clear()
        with patch(
            "loom.main.get_settings",
            return_value=_make_settings(),
        ):
            app = create_app()

        paths = [r.path for r in app.routes]
        assert any(p.startswith("/api/v1") for p in paths)
