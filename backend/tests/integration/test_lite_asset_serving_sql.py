"""real-SQL lite coverage: uploaded assets are viewable + downloadable.

reproduces the desktop bug where PDFs could not be previewed/downloaded
and video could not play: the download-url returned a ``loom://`` scheme
the webview can't load. now it returns a signed http url the sidecar's
own byte-serving endpoint validates and streams (with Range support so
video seeking works). this drives the whole chain end-to-end on a real
sqlite + LocalStorageBackend install with no minio and no temporal.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
import pytest_asyncio

import loom.config
from loom.security.rate_limit import limiter
from loom.workflows import shared

_MINIMAL_PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"

_ADMIN = {
    "admin_email": "admin@example.com",
    "admin_password": "correct-horse-battery",
    "admin_full_name": "Ada Admin",
}


@pytest.fixture(autouse=True)
def _reset_rate_limiter() -> None:
    limiter.reset()


@pytest.fixture
def lite_env(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[Path]:
    db_path = tmp_path / "loom.db"
    monkeypatch.setenv("LOOM_DEPLOYMENT_PROFILE", "lite")
    monkeypatch.setenv("LOOM_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("LOOM_DATABASE_URL", f"sqlite+aiosqlite:///{db_path}")
    monkeypatch.setenv("LOOM_SECRET_KEY", "x" * 48)
    monkeypatch.setenv("LOOM_STORAGE_SIGNING_SECRET", "y" * 48)

    loom.config.get_settings.cache_clear()
    shared.reset_for_testing()
    from loom.__main__ import bootstrap_schema_if_lite

    bootstrap_schema_if_lite()
    yield db_path
    loom.config.get_settings.cache_clear()
    shared.reset_for_testing()


@pytest_asyncio.fixture
async def lite_client(
    lite_env: Path,
) -> AsyncIterator[httpx.AsyncClient]:
    from loom.main import create_app

    app = create_app()
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac,
    ):
        yield ac


async def _auth(ac: httpx.AsyncClient) -> dict[str, str]:
    resp = await ac.post("/api/v1/first-run/complete", json=_ADMIN)
    assert resp.status_code == 201, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def _local_path(url: str) -> str:
    """strip the sidecar origin so the ASGITransport client can GET it."""
    marker = "/api/v1/"
    return url[url.index(marker) :]


async def _upload_pdf(
    ac: httpx.AsyncClient, headers: dict[str, str]
) -> tuple[str, str]:
    case = await ac.post(
        "/api/v1/cases",
        json={"name": "matter", "description": "d"},
        headers=headers,
    )
    assert case.status_code in (200, 201), case.text
    case_id = case.json()["id"]

    up = await ac.post(
        f"/api/v1/cases/{case_id}/assets/upload",
        files={"file": ("evidence.pdf", _MINIMAL_PDF, "application/pdf")},
        headers=headers,
    )
    assert up.status_code == 201, up.text
    return case_id, up.json()["id"]


@pytest.mark.asyncio
async def test_uploaded_pdf_is_servable_over_http(
    lite_client: httpx.AsyncClient,
) -> None:
    headers = await _auth(lite_client)
    case_id, asset_id = await _upload_pdf(lite_client, headers)

    # the download-url is now a signed http url, not loom://
    du = await lite_client.get(
        f"/api/v1/cases/{case_id}/assets/{asset_id}/download-url",
        headers=headers,
    )
    assert du.status_code == 200, du.text
    url = du.json()["url"]
    assert url.startswith("http://")
    assert "/api/v1/storage/object/" in url

    # the signed url streams the bytes with the right content type so
    # the webview renders the pdf inline. no auth header — the signature
    # is the credential.
    served = await lite_client.get(_local_path(url))
    assert served.status_code == 200, served.text
    assert served.headers["content-type"].startswith("application/pdf")
    assert served.headers.get("accept-ranges") == "bytes"
    assert served.content == _MINIMAL_PDF


@pytest.mark.asyncio
async def test_range_request_returns_206(
    lite_client: httpx.AsyncClient,
) -> None:
    headers = await _auth(lite_client)
    case_id, asset_id = await _upload_pdf(lite_client, headers)
    du = await lite_client.get(
        f"/api/v1/cases/{case_id}/assets/{asset_id}/download-url",
        headers=headers,
    )
    path = _local_path(du.json()["url"])

    ranged = await lite_client.get(path, headers={"Range": "bytes=0-3"})
    assert ranged.status_code == 206, ranged.text
    assert ranged.headers["content-range"] == f"bytes 0-3/{len(_MINIMAL_PDF)}"
    assert ranged.content == _MINIMAL_PDF[:4]


@pytest.mark.asyncio
async def test_tampered_signature_is_rejected(
    lite_client: httpx.AsyncClient,
) -> None:
    headers = await _auth(lite_client)
    case_id, asset_id = await _upload_pdf(lite_client, headers)
    du = await lite_client.get(
        f"/api/v1/cases/{case_id}/assets/{asset_id}/download-url",
        headers=headers,
    )
    path = _local_path(du.json()["url"])
    tampered = path[:-1] + ("0" if path[-1] != "0" else "1")
    resp = await lite_client.get(tampered)
    assert resp.status_code == 403
