"""the shipped verify.py must let opposing counsel or chambers
verify a court bundle with nothing but a python interpreter — no
loom install, no network, no third-party packages.
"""

import subprocess
import sys
import zipfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from loom.services.court_bundle import build_court_bundle

_CASE_ID = "01912345-6789-7abc-8def-012345678999"


def _stub_data() -> dict:
    return {
        "case": {"name": "Test Case", "description": None},
        "events": [],
        "annotations": [],
        "chain_of_custody": [
            {
                "asset_id": str(uuid4()),
                "exhibit_number": 1,
                "action": "ingest_verified",
                "actor_id": str(uuid4()),
                "timestamp": "2026-04-20T12:00:00+00:00",
                "detail": None,
            },
        ],
        "exhibits": [
            {
                "number": 1,
                "id": str(uuid4()),
                "original_filename": "evidence.mp4",
                "media_type": "video",
                "file_size_bytes": 1024,
                "sha256_hash": "a" * 64,
                "capture_time": "2026-04-20T12:00:00+00:00",
            },
        ],
        "preparer": "analyst@example.org",
        "generated_at": "2026-04-20T13:00:00+00:00",
        "date_range_start": None,
        "date_range_end": None,
    }


async def _build_bundle(tmp_path: Path) -> Path:
    session = MagicMock()
    dest = tmp_path / "bundle.zip"

    with (
        patch(
            "loom.services.court_bundle.build_court_bundle_data",
            new_callable=AsyncMock,
            return_value=_stub_data(),
        ),
        patch(
            "loom.services.court_bundle.render_report_pdf",
            side_effect=ImportError("forced html fallback"),
        ),
    ):
        await build_court_bundle(
            session,
            _CASE_ID,
            options={},
            storage=MagicMock(),
            dest_path=dest,
        )
    return dest


def _extract(zip_path: Path) -> Path:
    out = zip_path.parent / "extracted"
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(out)
    return out


def _run_verify(script: Path, target: Path) -> subprocess.CompletedProcess:
    # runs the interpreter we test under against the shipped
    # script; both arguments are test-controlled paths
    return subprocess.run(  # noqa: S603
        [sys.executable, str(script), str(target)],
        capture_output=True,
        text=True,
        timeout=120,
    )


class TestShippedVerifier:
    @pytest.mark.asyncio
    async def test_intact_extracted_bundle_passes(self, tmp_path: Path) -> None:
        bundle_dir = _extract(await _build_bundle(tmp_path))
        result = _run_verify(bundle_dir / "verify.py", bundle_dir)
        assert result.returncode == 0, result.stdout + result.stderr
        assert "OK" in result.stdout

    @pytest.mark.asyncio
    async def test_intact_zip_passes(self, tmp_path: Path) -> None:
        zip_path = await _build_bundle(tmp_path)
        bundle_dir = _extract(zip_path)
        result = _run_verify(bundle_dir / "verify.py", zip_path)
        assert result.returncode == 0, result.stdout + result.stderr

    @pytest.mark.asyncio
    async def test_tampered_file_fails_and_is_named(
        self, tmp_path: Path
    ) -> None:
        bundle_dir = _extract(await _build_bundle(tmp_path))
        victim = bundle_dir / "chain_of_custody.json"
        raw = bytearray(victim.read_bytes())
        raw[0] ^= 0xFF
        victim.write_bytes(bytes(raw))

        result = _run_verify(bundle_dir / "verify.py", bundle_dir)
        assert result.returncode != 0
        output = result.stdout + result.stderr
        assert "chain_of_custody.json" in output
        assert "MISMATCH" in output

    @pytest.mark.asyncio
    async def test_missing_listed_file_fails(self, tmp_path: Path) -> None:
        bundle_dir = _extract(await _build_bundle(tmp_path))
        (bundle_dir / "declaration.txt").unlink()

        result = _run_verify(bundle_dir / "verify.py", bundle_dir)
        assert result.returncode != 0
        output = result.stdout + result.stderr
        assert "declaration.txt" in output
        assert "MISSING" in output

    @pytest.mark.asyncio
    async def test_unlisted_file_is_reported_but_not_fatal(
        self, tmp_path: Path
    ) -> None:
        """os droppings (thumbs.db, .DS_Store) must not break a
        production, but the verifier has to surface them."""
        bundle_dir = _extract(await _build_bundle(tmp_path))
        (bundle_dir / "Thumbs.db").write_bytes(b"windows was here")

        result = _run_verify(bundle_dir / "verify.py", bundle_dir)
        assert result.returncode == 0
        assert "Thumbs.db" in result.stdout
        assert "UNLISTED" in result.stdout
