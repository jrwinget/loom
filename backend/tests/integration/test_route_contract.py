"""frontend<->backend route-contract guard.

three shipped bugs were the frontend calling a path the backend does
not serve (`/assets` vs `/assets/upload`, `useAsset` vs case-scoped,
`/download` vs `/download-url`). hook tests mock apiClient, so they
never catch this. this test extracts every literal API path the
frontend calls and asserts it resolves against the FastAPI route
table — failing CI on any drift.

it is deliberately conservative: only literal string/template paths
are checked (dynamically-built urls are skipped), so it never false-
positives on un-parseable calls.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from loom.main import create_app

_REPO_ROOT = Path(__file__).resolve().parents[3]
_FRONTEND_SRC = _REPO_ROOT / "frontend" / "src"
_API_PREFIX = "/api/v1"

# apiClient.get<T>(`/path`) / .post('/path') / ...
_API_CALL = re.compile(
    r"apiClient\.(get|post|put|patch|delete)\s*"
    r"(?:<[^>]*>)?\s*\(\s*[`'\"]([^`'\"]+)[`'\"]"
)
# xhr.open('POST', `${getApiOrigin()}/path`)
_XHR_CALL = re.compile(
    r"\.open\(\s*['\"]([A-Z]+)['\"]\s*,\s*[`'\"]([^`'\"]+)[`'\"]"
)


def _normalize_call_path(raw: str) -> str | None:
    """reduce a frontend path template to a comparable route shape.

    returns None when the path is not a concrete api path we can check.
    """
    path = raw.replace("${getApiOrigin()}", "")
    # a real path param is its own segment (`/${id}`). an interpolation
    # glued to surrounding text (`assets${qs}`) is a dynamically-built
    # query/suffix we can't verify — skip those calls rather than risk a
    # false positive.
    if re.search(r"[^/]\$\{", path):
        return None
    path = re.sub(r"\$\{[^}]*\}", "{}", path)  # clean-segment params -> {}
    path = path.split("?", 1)[0]  # drop literal query string
    # a leftover '$' means the capture truncated on a quote inside an
    # interpolation (e.g. `${jobId ?? ''}`) — can't verify, so skip.
    if "$" in path or not path.startswith("/"):
        return None
    return path.rstrip("/") or "/"


def _normalize_route_path(path: str) -> str:
    if path.startswith(_API_PREFIX):
        path = path[len(_API_PREFIX) :]
    path = re.sub(r"\{[^}]*\}", "{}", path)
    return path.rstrip("/") or "/"


_HTTP_METHODS = {"get", "post", "put", "patch", "delete", "head", "options"}


def _backend_routes() -> set[tuple[str, str]]:
    # the openapi schema is the canonical, fully-resolved route table
    # (app.routes lazily nests the included router, so it can't be
    # walked directly).
    schema = create_app().openapi()
    pairs: set[tuple[str, str]] = set()
    for path, ops in schema.get("paths", {}).items():
        if not path.startswith(_API_PREFIX):
            continue
        norm = _normalize_route_path(path)
        for method in ops:
            if method.lower() in _HTTP_METHODS:
                pairs.add((method.upper(), norm))
    return pairs


def _is_test_file(file: Path) -> bool:
    parts = set(file.parts)
    return (
        "__tests__" in parts
        or "__mocks__" in parts
        or ".test." in file.name
        or ".spec." in file.name
    )


def _frontend_calls() -> list[tuple[str, str, Path]]:
    calls: list[tuple[str, str, Path]] = []
    for ext in ("*.ts", "*.tsx"):
        for file in _FRONTEND_SRC.rglob(ext):
            if _is_test_file(file):
                continue
            text = file.read_text(encoding="utf-8")
            for method, raw in _API_CALL.findall(text):
                norm = _normalize_call_path(raw)
                if norm:
                    calls.append((method.upper(), norm, file))
            for method, raw in _XHR_CALL.findall(text):
                norm = _normalize_call_path(raw)
                if norm and norm.startswith("/cases"):
                    calls.append((method.upper(), norm, file))
    return calls


@pytest.mark.skipif(
    not _FRONTEND_SRC.is_dir(), reason="frontend source not present"
)
def test_every_frontend_api_path_resolves_to_a_route() -> None:
    routes = _backend_routes()
    calls = _frontend_calls()
    assert calls, "extracted no frontend api calls — extractor is broken"

    violations = sorted(
        {
            f"{method} {path}  ({file.relative_to(_REPO_ROOT)})"
            for method, path, file in calls
            if (method, path) not in routes
        }
    )
    assert not violations, (
        "frontend calls paths the backend does not serve:\n  "
        + "\n  ".join(violations)
    )
