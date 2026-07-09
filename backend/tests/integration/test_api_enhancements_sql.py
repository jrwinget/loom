"""real-SQL lite coverage for the clarity-assist enhancement api.

boots a lite sqlite db with the LocalStorageBackend (no minio, no
temporal) and drives the enhancement endpoints end-to-end: suggest
parameters from a measured sample, dispatch a run, list produced
derivatives, and reject a non-member. the ffmpeg-calling analysis is
monkeypatched so the suite needs no ffmpeg binary.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import select

import loom.config
from loom.security.auth import create_access_token
from loom.security.rate_limit import limiter
from loom.services.enhancement import (
    EnhancementParams,
    VideoStats,
    enhancement_provenance,
)
from loom.services.storage_backends import (
    ORIGINALS_BUCKET,
)
from loom.workflows import shared

_ADMIN = {
    "admin_email": "admin@example.com",
    "admin_password": "correct-horse-battery",
    "admin_full_name": "Ada Admin",
}

# a dark, flat, noisy, interlaced, low-res sample: every heuristic
# threshold fires, so suggest returns a non-neutral value with a
# reason for each one
_STATS = VideoStats(
    yavg=30.0,
    ymin=10.0,
    ymax=80.0,
    ydif=15.0,
    interlaced=True,
    height=480,
)


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


async def _admin_user_id() -> str:
    from loom.models.user import User

    async with shared.get_db_session() as session:
        result = await session.execute(select(User.id))
        return str(result.scalars().first())


async def _create_case(ac: httpx.AsyncClient, headers: dict[str, str]) -> str:
    resp = await ac.post(
        "/api/v1/cases",
        json={"name": "matter", "description": "d"},
        headers=headers,
    )
    assert resp.status_code in (200, 201), resp.text
    return str(resp.json()["id"])


async def _seed_video_asset(case_id: str, user_id: str) -> str:
    from loom.models.asset import Asset

    asset_id = uuid.uuid4()
    storage_key = f"{case_id}/{asset_id}/original.mp4"
    storage = shared.get_storage_backend()
    storage.upload_bytes(
        ORIGINALS_BUCKET, storage_key, b"fake-mp4-bytes", "video/mp4"
    )
    async with shared.get_db_session() as session:
        session.add(
            Asset(
                id=asset_id,
                case_id=uuid.UUID(case_id),
                original_filename="clip.mp4",
                storage_key=storage_key,
                media_type="video",
                mime_type="video/mp4",
                file_size_bytes=14,
                sha256_hash="0" * 64,
                sha512_hash="0" * 128,
                upload_status="complete",
                uploaded_by=uuid.UUID(user_id),
                processing_status="complete",
            )
        )
        await session.commit()
    return str(asset_id)


async def _seed_enhancement(asset_id: str) -> None:
    from loom.models.derivative import Derivative

    provenance = enhancement_provenance(EnhancementParams(brightness=0.2))
    async with shared.get_db_session() as session:
        session.add(
            Derivative(
                asset_id=uuid.UUID(asset_id),
                type="enhancement",
                storage_key=f"enhancements/{asset_id}/{uuid.uuid4()}.mp4",
                mime_type="video/mp4",
                file_size_bytes=123,
                sha256_hash="a" * 64,
                generation_params=provenance,
            )
        )
        await session.commit()


@pytest.mark.asyncio
async def test_suggest_returns_params_and_reasons(
    lite_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers = await _auth(lite_client)
    case_id = await _create_case(lite_client, headers)
    asset_id = await _seed_video_asset(case_id, await _admin_user_id())

    monkeypatch.setattr(
        "loom.api.v1.enhancements.analyze_video",
        lambda _src: _STATS,
    )

    resp = await lite_client.get(
        f"/api/v1/cases/{case_id}/assets/{asset_id}/enhancements/suggest",
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    # backend serialises snake_case; the frontend api-client camelCases
    params = body["params"]
    assert params["gamma"] == 1.4
    assert params["denoise"] == 4
    assert params["deinterlace"] is True
    assert params["scale_factor"] == 2
    # one human reason per non-neutral suggestion
    assert len(body["reasons"]) == 6
    assert any("deinterlace" in r for r in body["reasons"])


@pytest.mark.asyncio
async def test_suggest_rejects_non_video(
    lite_client: httpx.AsyncClient,
) -> None:
    headers = await _auth(lite_client)
    case_id = await _create_case(lite_client, headers)
    user_id = await _admin_user_id()

    from loom.models.asset import Asset

    asset_id = uuid.uuid4()
    async with shared.get_db_session() as session:
        session.add(
            Asset(
                id=asset_id,
                case_id=uuid.UUID(case_id),
                original_filename="doc.pdf",
                storage_key=f"{case_id}/{asset_id}/original.pdf",
                media_type="document",
                mime_type="application/pdf",
                file_size_bytes=1,
                sha256_hash="0" * 64,
                sha512_hash="0" * 128,
                upload_status="complete",
                uploaded_by=uuid.UUID(user_id),
                processing_status="complete",
            )
        )
        await session.commit()

    resp = await lite_client.get(
        f"/api/v1/cases/{case_id}/assets/{asset_id}/enhancements/suggest",
        headers=headers,
    )
    assert resp.status_code == 409, resp.text


@pytest.mark.asyncio
async def test_post_dispatches_enhancement(
    lite_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers = await _auth(lite_client)
    case_id = await _create_case(lite_client, headers)
    asset_id = await _seed_video_asset(case_id, await _admin_user_id())

    calls: dict[str, object] = {}

    async def fake_dispatch(name: str, **kwargs: object) -> object:
        calls["name"] = name
        calls["args"] = kwargs.get("args")
        calls["workflow_id"] = kwargs.get("workflow_id")
        return object()

    monkeypatch.setattr(
        "loom.api.v1.enhancements.dispatch_workflow", fake_dispatch
    )

    resp = await lite_client.post(
        f"/api/v1/cases/{case_id}/assets/{asset_id}/enhancements",
        json={"brightness": 0.1, "scale_factor": 2},
        headers=headers,
    )
    assert resp.status_code == 202, resp.text
    body = resp.json()
    assert body["workflow_id"].startswith(f"enhance-{asset_id}-")
    assert body["params"]["scale_factor"] == 2
    assert body["params"]["brightness"] == 0.1
    # the router dispatched the enhancement workflow with the asset id
    assert calls["name"] == "enhancement"
    assert calls["args"][0] == asset_id  # type: ignore[index]
    assert calls["workflow_id"] == body["workflow_id"]


@pytest.mark.asyncio
async def test_list_returns_seeded_enhancement(
    lite_client: httpx.AsyncClient,
) -> None:
    headers = await _auth(lite_client)
    case_id = await _create_case(lite_client, headers)
    asset_id = await _seed_video_asset(case_id, await _admin_user_id())
    await _seed_enhancement(asset_id)

    resp = await lite_client.get(
        f"/api/v1/cases/{case_id}/assets/{asset_id}/enhancements",
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    items = resp.json()["enhancements"]
    assert len(items) == 1
    item = items[0]
    assert item["download_url"].startswith("http")
    assert item["generation_params"]["model_params"]["filter_chain"] == (
        "eq=brightness=0.2"
    )


@pytest.mark.asyncio
async def test_non_member_forbidden(
    lite_client: httpx.AsyncClient,
) -> None:
    headers = await _auth(lite_client)
    case_id = await _create_case(lite_client, headers)
    asset_id = await _seed_video_asset(case_id, await _admin_user_id())

    outsider = create_access_token(str(uuid.uuid4()), "viewer")
    resp = await lite_client.get(
        f"/api/v1/cases/{case_id}/assets/{asset_id}/enhancements",
        headers={"Authorization": f"Bearer {outsider}"},
    )
    assert resp.status_code == 403, resp.text
