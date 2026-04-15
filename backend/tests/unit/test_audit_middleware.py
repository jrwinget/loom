"""tests for audit middleware."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest

from loom.security.audit import AuditMiddleware


def _make_scope(
    method: str = "POST",
    path: str = "/api/v1/cases",
    headers: list[tuple[bytes, bytes]] | None = None,
) -> dict:
    """build a minimal asgi scope."""
    if headers is None:
        headers = []
    return {
        "type": "http",
        "method": method,
        "path": path,
        "query_string": b"",
        "root_path": "",
        "headers": headers,
        "server": ("127.0.0.1", 8000),
        "client": ("127.0.0.1", 12345),
    }


class TestSkipMethods:
    """middleware skips GET/OPTIONS/HEAD requests."""

    @pytest.mark.asyncio
    async def test_skips_get(self) -> None:
        """GET request passes through without logging."""
        inner = AsyncMock()
        mw = AuditMiddleware(inner)
        scope = _make_scope(method="GET")
        receive = AsyncMock()
        send = AsyncMock()

        await mw(scope, receive, send)
        inner.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_skips_options(self) -> None:
        """OPTIONS request passes through without logging."""
        inner = AsyncMock()
        mw = AuditMiddleware(inner)
        scope = _make_scope(method="OPTIONS")
        receive = AsyncMock()
        send = AsyncMock()

        await mw(scope, receive, send)
        inner.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_skips_head(self) -> None:
        """HEAD request passes through without logging."""
        inner = AsyncMock()
        mw = AuditMiddleware(inner)
        scope = _make_scope(method="HEAD")
        receive = AsyncMock()
        send = AsyncMock()

        await mw(scope, receive, send)
        inner.assert_awaited_once()


class TestMutatingMethods:
    """middleware logs POST/PATCH/DELETE requests."""

    @pytest.mark.asyncio
    async def test_logs_post(self) -> None:
        """POST request triggers audit logging."""
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session_factory = MagicMock()
        mock_session_factory.return_value.__aenter__ = AsyncMock(
            return_value=mock_session
        )
        mock_session_factory.return_value.__aexit__ = AsyncMock(
            return_value=False
        )

        mock_app_state = MagicMock()
        mock_app_state.db_session_factory = mock_session_factory

        async def inner(scope: dict, receive: object, send: object) -> None:
            # send the response start
            await send(  # type: ignore[operator]
                {"type": "http.response.start", "status": 201}
            )
            await send(  # type: ignore[operator]
                {"type": "http.response.body", "body": b"ok"}
            )

        mw = AuditMiddleware(inner)
        scope = _make_scope(method="POST", path="/api/v1/cases")
        # inject mock app state
        scope["app"] = MagicMock()
        scope["app"].state = mock_app_state
        receive = AsyncMock()
        send = AsyncMock()

        await mw(scope, receive, send)

        mock_session.add.assert_called_once()
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_logs_delete(self) -> None:
        """DELETE request triggers audit logging."""
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session_factory = MagicMock()
        mock_session_factory.return_value.__aenter__ = AsyncMock(
            return_value=mock_session
        )
        mock_session_factory.return_value.__aexit__ = AsyncMock(
            return_value=False
        )

        mock_app_state = MagicMock()
        mock_app_state.db_session_factory = mock_session_factory

        async def inner(scope: dict, receive: object, send: object) -> None:
            await send(  # type: ignore[operator]
                {"type": "http.response.start", "status": 204}
            )
            await send(  # type: ignore[operator]
                {"type": "http.response.body", "body": b""}
            )

        mw = AuditMiddleware(inner)
        rid = "01912345-6789-7abc-8def-0123456789ab"
        scope = _make_scope(
            method="DELETE",
            path=f"/api/v1/cases/{rid}",
        )
        scope["app"] = MagicMock()
        scope["app"].state = mock_app_state
        receive = AsyncMock()
        send = AsyncMock()

        await mw(scope, receive, send)
        mock_session.add.assert_called_once()


class TestJwtExtraction:
    """extracts actor_id from JWT when present."""

    @pytest.mark.asyncio
    async def test_extracts_actor_from_jwt(self) -> None:
        """valid jwt extracts actor_id."""
        user_id = "01912345-6789-7abc-8def-012345678901"
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session_factory = MagicMock()
        mock_session_factory.return_value.__aenter__ = AsyncMock(
            return_value=mock_session
        )
        mock_session_factory.return_value.__aexit__ = AsyncMock(
            return_value=False
        )

        mock_app_state = MagicMock()
        mock_app_state.db_session_factory = mock_session_factory

        async def inner(scope: dict, receive: object, send: object) -> None:
            await send(  # type: ignore[operator]
                {"type": "http.response.start", "status": 200}
            )
            await send(  # type: ignore[operator]
                {"type": "http.response.body", "body": b"ok"}
            )

        mw = AuditMiddleware(inner)
        scope = _make_scope(
            method="POST",
            path="/api/v1/cases",
            headers=[
                (b"authorization", b"Bearer fake-token"),
            ],
        )
        scope["app"] = MagicMock()
        scope["app"].state = mock_app_state
        receive = AsyncMock()
        send = AsyncMock()

        with patch(
            "loom.security.audit.decode_token",
            return_value={"sub": user_id},
        ):
            await mw(scope, receive, send)

        added = mock_session.add.call_args[0][0]
        assert added.actor_id == UUID(user_id)


class TestResourceParsing:
    """extracts resource info from URL path."""

    @pytest.mark.asyncio
    async def test_extracts_resource_type(self) -> None:
        """parses resource type from path."""
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session_factory = MagicMock()
        mock_session_factory.return_value.__aenter__ = AsyncMock(
            return_value=mock_session
        )
        mock_session_factory.return_value.__aexit__ = AsyncMock(
            return_value=False
        )

        mock_app_state = MagicMock()
        mock_app_state.db_session_factory = mock_session_factory

        async def inner(scope: dict, receive: object, send: object) -> None:
            await send(  # type: ignore[operator]
                {"type": "http.response.start", "status": 200}
            )
            await send(  # type: ignore[operator]
                {"type": "http.response.body", "body": b"ok"}
            )

        mw = AuditMiddleware(inner)
        rid = "01912345-6789-7abc-8def-0123456789ab"
        scope = _make_scope(
            method="PATCH",
            path=f"/api/v1/cases/{rid}",
        )
        scope["app"] = MagicMock()
        scope["app"].state = mock_app_state
        receive = AsyncMock()
        send = AsyncMock()

        with patch(
            "loom.security.audit.decode_token",
            side_effect=Exception("no token"),
        ):
            await mw(scope, receive, send)

        added = mock_session.add.call_args[0][0]
        assert added.resource_type == "cases"
        assert added.resource_id == UUID(rid)


class TestMissingAuth:
    """handles missing auth header gracefully."""

    @pytest.mark.asyncio
    async def test_no_auth_header(self) -> None:
        """proceeds without error when no auth header."""
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session_factory = MagicMock()
        mock_session_factory.return_value.__aenter__ = AsyncMock(
            return_value=mock_session
        )
        mock_session_factory.return_value.__aexit__ = AsyncMock(
            return_value=False
        )

        mock_app_state = MagicMock()
        mock_app_state.db_session_factory = mock_session_factory

        async def inner(scope: dict, receive: object, send: object) -> None:
            await send(  # type: ignore[operator]
                {"type": "http.response.start", "status": 200}
            )
            await send(  # type: ignore[operator]
                {"type": "http.response.body", "body": b"ok"}
            )

        mw = AuditMiddleware(inner)
        scope = _make_scope(method="POST", path="/api/v1/cases")
        scope["app"] = MagicMock()
        scope["app"].state = mock_app_state
        receive = AsyncMock()
        send = AsyncMock()

        await mw(scope, receive, send)

        added = mock_session.add.call_args[0][0]
        assert added.actor_id is None

    @pytest.mark.asyncio
    async def test_no_session_factory(self) -> None:
        """handles missing db_session_factory gracefully."""

        async def inner(scope: dict, receive: object, send: object) -> None:
            await send(  # type: ignore[operator]
                {"type": "http.response.start", "status": 200}
            )
            await send(  # type: ignore[operator]
                {"type": "http.response.body", "body": b"ok"}
            )

        mw = AuditMiddleware(inner)
        scope = _make_scope(method="POST", path="/api/v1/cases")
        scope["app"] = MagicMock()
        scope["app"].state = MagicMock(
            spec=[],  # no db_session_factory attr
        )
        receive = AsyncMock()
        send = AsyncMock()

        # should not raise
        await mw(scope, receive, send)

    @pytest.mark.asyncio
    async def test_non_http_scope(self) -> None:
        """websocket scope passes through."""
        inner = AsyncMock()
        mw = AuditMiddleware(inner)
        scope = {"type": "websocket"}
        receive = AsyncMock()
        send = AsyncMock()

        await mw(scope, receive, send)
        inner.assert_awaited_once()
