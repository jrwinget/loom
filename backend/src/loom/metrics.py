"""prometheus metrics for the loom backend.

all metric objects are module-level singletons so any module
can import and use them without passing state around.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from prometheus_client import Counter, Gauge, Histogram

if TYPE_CHECKING:
    from starlette.requests import HTTPConnection
    from starlette.types import Scope


class _NoOpHistogram:
    """drop-in replacement when prometheus_client is absent."""

    def labels(self, **_kwargs: Any) -> _NoOpHistogram:
        return self

    def observe(self, _value: float) -> None:
        pass


class _NoOpCounter:
    """drop-in replacement when prometheus_client is absent."""

    def labels(self, **_kwargs: Any) -> _NoOpCounter:
        return self

    def inc(self, _value: float = 1) -> None:
        pass


class _NoOpGauge:
    """drop-in replacement when prometheus_client is absent."""

    def set(self, _value: float) -> None:
        pass

    def inc(self, _value: float = 1) -> None:
        pass

    def dec(self, _value: float = 1) -> None:
        pass


# -- upload tracking --
active_uploads = Gauge(
    "loom_active_uploads",
    "number of in-progress file uploads",
)

# -- ingest pipeline --
ingest_workflow_duration = Histogram(
    "loom_ingest_workflow_duration_seconds",
    "duration of ingest workflow activities",
    ["activity"],
    buckets=(0.1, 0.5, 1, 2, 5, 10, 30, 60, 120, 300),
)

# -- audit --
audit_failures = Counter(
    "loom_audit_failures_total",
    "number of failed audit log writes",
)

# -- auth --
auth_failures = Counter(
    "loom_auth_failures_total",
    "authentication failures by type",
    ["reason"],
)

# -- db pool --
db_pool_size = Gauge(
    "loom_db_pool_size",
    "total connections in the sqlalchemy pool",
)

db_pool_checked_out = Gauge(
    "loom_db_pool_checked_out",
    "connections currently checked out of the pool",
)


def _resolve_route_name(routes: list[Any], scope: Scope) -> str | None:
    """resolve the templated route name for a request scope.

    fastapi 0.137 stopped flattening nested ``include_router`` calls
    into ``app.routes``; an included router now appears as a single
    ``_IncludedRouter`` entry that matches requests but exposes no
    ``.path``. prometheus-fastapi-instrumentator (8.0.0, latest) still
    reads ``route.path`` directly and raises on the new entry. walk the
    included router's effective candidates so metric labels keep their
    low-cardinality templated paths.
    """
    from fastapi.routing import _IncludedRouter
    from starlette.routing import Match, Mount

    for route in routes:
        match, child_scope = route.matches(scope)
        if match != Match.FULL:
            continue
        merged = {**scope, **child_scope}
        if isinstance(route, _IncludedRouter):
            return _resolve_route_name(route.effective_candidates(), merged)
        segment = getattr(route, "path", None) or getattr(
            route, "path_format", None
        )
        if isinstance(route, Mount) and route.routes:
            child = _resolve_route_name(route.routes, merged)
            return f"{segment}{child}" if child else None
        return segment
    return None


def install_route_name_compat() -> None:
    """patch the instrumentator's route resolver for fastapi 0.137.

    the upstream resolver cannot see through ``_IncludedRouter``; until a
    compatible release ships, route this through ``_resolve_route_name``.
    """
    from prometheus_fastapi_instrumentator import routing

    def get_route_name(request: HTTPConnection) -> str | None:
        return _resolve_route_name(request.app.routes, request.scope)

    routing.get_route_name = get_route_name
