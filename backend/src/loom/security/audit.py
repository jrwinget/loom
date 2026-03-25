import re
from uuid import UUID

import structlog
from starlette.requests import Request
from starlette.types import ASGIApp, Receive, Scope, Send

from loom.models.audit import AuditLogEntry
from loom.security.auth import decode_token

log = structlog.get_logger()

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}"
    r"-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)

_SKIP_METHODS = {"GET", "OPTIONS", "HEAD"}


class AuditMiddleware:
    """asgi middleware that logs mutating requests."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive, send)
        method = request.method

        if method in _SKIP_METHODS:
            await self.app(scope, receive, send)
            return

        # capture status code from response
        status_code = 500
        original_send = send

        async def capture_send(message: dict) -> None:  # type: ignore[type-arg]
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
            await original_send(message)

        await self.app(scope, receive, capture_send)

        # log audit entry after response
        await self._log_audit(request, method, status_code)

    async def _log_audit(
        self,
        request: Request,
        method: str,
        status_code: int,
    ) -> None:
        """write an audit log entry to the database."""
        try:
            session_factory = request.app.state.db_session_factory
        except AttributeError:
            return

        if session_factory is None:
            return

        # extract actor from jwt if present
        actor_id = None
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            try:
                payload = decode_token(auth_header.removeprefix("Bearer "))
                actor_id = UUID(payload["sub"])
            except Exception:
                await log.adebug("could not extract actor from jwt")

        # parse path segments after /api/v1/
        path = request.url.path
        segments = [s for s in path.split("/") if s]
        # find segments after "v1"
        resource_type = ""
        resource_id = None
        try:
            v1_idx = segments.index("v1")
            rest = segments[v1_idx + 1 :]
            if rest:
                resource_type = rest[0]
            if len(rest) > 1 and _UUID_RE.match(rest[1]):
                resource_id = UUID(rest[1])
        except ValueError:
            pass

        action = f"{method} {path}"
        ip_address = request.client.host if request.client else None
        user_agent = request.headers.get("User-Agent")

        try:
            async with session_factory() as session:
                entry = AuditLogEntry(
                    actor_id=actor_id,
                    action=action,
                    resource_type=resource_type or "unknown",
                    resource_id=resource_id,
                    ip_address=ip_address,
                    user_agent=user_agent,
                    detail={"status_code": status_code},
                )
                session.add(entry)
                await session.commit()
        except Exception:
            await log.awarning(
                "failed to write audit log entry",
                action=action,
            )
