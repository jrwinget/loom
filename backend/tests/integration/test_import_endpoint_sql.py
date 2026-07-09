"""the import endpoint verifies before it creates and refuses a
duplicate bundle — the two properties that keep import safe and
idempotent."""

from __future__ import annotations

import io
import zipfile
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
import pytest_asyncio

import loom.config
from loom.security.rate_limit import limiter


@pytest.fixture(autouse=True)
def _reset_rate_limiter() -> None:
    limiter.reset()


@pytest.fixture
def lite_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[Path]:
    db_path = tmp_path / "loom.db"
    monkeypatch.setenv("LOOM_DEPLOYMENT_PROFILE", "lite")
    monkeypatch.setenv("LOOM_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("LOOM_DATABASE_URL", f"sqlite+aiosqlite:///{db_path}")
    monkeypatch.setenv("LOOM_SECRET_KEY", "x" * 48)
    monkeypatch.setenv("LOOM_STORAGE_SIGNING_SECRET", "y" * 48)
    loom.config.get_settings.cache_clear()
    from loom.__main__ import bootstrap_schema_if_lite

    bootstrap_schema_if_lite()
    yield tmp_path
    loom.config.get_settings.cache_clear()


@pytest_asyncio.fixture
async def lite_client(lite_env: Path) -> AsyncIterator[httpx.AsyncClient]:
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


async def _admin_headers(client: httpx.AsyncClient) -> dict[str, str]:
    resp = await client.post(
        "/api/v1/first-run/complete",
        json={
            "admin_email": "ada@example.org",
            "admin_password": "correct-horse-battery",
            "admin_full_name": "Ada Admin",
        },
    )
    assert resp.status_code == 201, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def _minimal_bundle() -> bytes:
    """a valid, unsigned, empty-case bundle with a correct manifest."""
    import hashlib
    import json

    docs = {
        "bundle.json": {"format_version": 1, "source_deploy": "peer"},
        "data/case.json": {"name": "Imported", "description": None},
        "data/assets.json": [],
        "data/timeline.json": {"events": [], "evidence_links": []},
        "data/annotations.json": [],
        "data/transcripts.json": [],
        "data/custody.json": [],
    }
    bodies = {
        name: json.dumps(payload, indent=2, sort_keys=True).encode()
        for name, payload in docs.items()
    }
    manifest = (
        "\n".join(
            f"{hashlib.sha256(bodies[n]).hexdigest()}  {n}"
            for n in sorted(bodies)
        )
        + "\n"
    ).encode()

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, body in bodies.items():
            zf.writestr(name, body)
        zf.writestr("MANIFEST.sha256", manifest)
    return buf.getvalue()


async def _post_bundle(
    client: httpx.AsyncClient, headers: dict[str, str], data: bytes
) -> httpx.Response:
    return await client.post(
        "/api/v1/imports/bundle",
        content=data,
        headers={**headers, "Content-Type": "application/octet-stream"},
    )


@pytest.mark.asyncio
async def test_import_creates_case_and_is_idempotent(
    lite_client: httpx.AsyncClient,
) -> None:
    headers = await _admin_headers(lite_client)
    bundle = _minimal_bundle()

    first = await _post_bundle(lite_client, headers, bundle)
    assert first.status_code == 202, first.text
    body = first.json()
    assert body["case_id"]
    assert body["workflow_id"] == f"bundle-import-{body['case_id']}"
    assert body["signature_status"] == "unsigned"

    # the same bundle a second time is refused, not duplicated
    second = await _post_bundle(lite_client, headers, bundle)
    assert second.status_code == 409, second.text


@pytest.mark.asyncio
async def test_tampered_bundle_rejected_before_creating_a_case(
    lite_client: httpx.AsyncClient,
) -> None:
    headers = await _admin_headers(lite_client)
    good = _minimal_bundle()

    # flip a byte inside a data document so its manifest hash breaks
    buf = io.BytesIO()
    with (
        zipfile.ZipFile(io.BytesIO(good)) as src,
        zipfile.ZipFile(buf, "w") as dst,
    ):
        for name in src.namelist():
            data = src.read(name)
            if name == "data/case.json":
                data = data.replace(b"Imported", b"Tampered!")
            dst.writestr(name, data)

    resp = await _post_bundle(lite_client, headers, buf.getvalue())
    assert resp.status_code == 422, resp.text
    assert "verification" in resp.json()["detail"]
