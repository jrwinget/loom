import hashlib
import zipfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from loom.services.court_bundle import (
    _render_manifest_lines,
    build_court_bundle,
)
from loom.services.portable_bundle import BundleVerificationError

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
        "preparer": str(uuid4()),
        "generated_at": "2026-04-20T13:00:00+00:00",
        "date_range_start": None,
        "date_range_end": None,
    }


def _report_stub() -> dict:
    return {
        "case": {"name": "C", "description": None},
        "events": [],
        "annotations": [],
        "chain_of_custody": [],
        "assets": [],
        "generated_at": "2026-04-20T13:00:00+00:00",
        "executive_summary": None,
        "date_range_start": None,
        "date_range_end": None,
    }


class TestRenderManifestLines:
    def test_lines_are_sorted_and_deterministic(self) -> None:
        entries = {
            "b.pdf": "1" * 64,
            "a.pdf": "2" * 64,
            "c.pdf": "3" * 64,
        }
        manifest = _render_manifest_lines(entries)
        # lines sorted by path so two runs produce identical output
        lines = manifest.strip().split("\n")
        paths = [line.split("  ")[1] for line in lines]
        assert paths == ["a.pdf", "b.pdf", "c.pdf"]

    def test_hashes_appear_verbatim(self) -> None:
        digest = hashlib.sha256(b"hello world").hexdigest()
        manifest = _render_manifest_lines({"greet.txt": digest})
        assert digest in manifest

    def test_trailing_newline_present(self) -> None:
        # sha256sum-compatible format has a trailing newline
        manifest = _render_manifest_lines({"x.txt": "0" * 64})
        assert manifest.endswith("\n")


class TestBuildCourtBundle:
    @pytest.mark.asyncio
    async def test_default_bundle_is_evidence_only(
        self, tmp_path: Path
    ) -> None:
        """the default court bundle is an evidence-only production:
        no report.pdf (attorney work product), but the custody log
        travels with it. every manifest hash matches its file.
        """
        session = MagicMock()
        dest = tmp_path / "bundle.zip"

        with patch(
            "loom.services.court_bundle.build_court_bundle_data",
            new_callable=AsyncMock,
            return_value=_stub_data(),
        ):
            sha256, exported = await build_court_bundle(
                session,
                _CASE_ID,
                options={},
                storage=MagicMock(),
                dest_path=dest,
                preparer="analyst@example.org",
            )

        assert len(sha256) == 64
        assert exported == []
        assert hashlib.sha256(dest.read_bytes()).hexdigest() == sha256

        with zipfile.ZipFile(dest) as zf:
            names = set(zf.namelist())
            assert {
                "cover.pdf",
                "exhibit_index.pdf",
                "chain_of_custody.json",
                "MANIFEST.sha256",
            }.issubset(names)
            assert "report.pdf" not in names

            manifest = zf.read("MANIFEST.sha256").decode("utf-8")
            for line in manifest.strip().splitlines():
                digest, path = line.split("  ", 1)
                file_bytes = zf.read(path)
                assert hashlib.sha256(file_bytes).hexdigest() == digest, (
                    f"manifest hash mismatch for {path}"
                )

    @pytest.mark.asyncio
    async def test_analysis_opt_in_ships_work_product_report(
        self, tmp_path: Path
    ) -> None:
        """include_analysis=True adds report.pdf with the banner."""
        session = MagicMock()
        dest = tmp_path / "bundle.zip"

        with (
            patch(
                "loom.services.court_bundle.build_court_bundle_data",
                new_callable=AsyncMock,
                return_value=_stub_data(),
            ),
            patch(
                "loom.services.report.build_report_data",
                new_callable=AsyncMock,
                return_value=_report_stub(),
            ),
            patch(
                "loom.services.court_bundle.render_report_pdf",
                side_effect=ImportError("forced html fallback"),
            ),
        ):
            await build_court_bundle(
                session,
                _CASE_ID,
                options={"include_analysis": True},
                storage=MagicMock(),
                dest_path=dest,
            )

        with zipfile.ZipFile(dest) as zf:
            names = set(zf.namelist())
            assert "report.pdf" in names
            report = zf.read("report.pdf").decode("utf-8")
        # html fallback bytes carry the banner text
        assert "ATTORNEY WORK PRODUCT" in report

    @pytest.mark.asyncio
    async def test_originals_streamed_verified_and_numbered(
        self, tmp_path: Path
    ) -> None:
        """include_originals streams exhibits with stable numbering
        and re-verifies each against the recorded ingest hash."""
        session = MagicMock()
        dest = tmp_path / "bundle.zip"
        payload = b"original evidence bytes"
        sha = hashlib.sha256(payload).hexdigest()

        asset = MagicMock()
        asset.id = uuid4()
        asset.original_filename = "evidence.mp4"
        asset.storage_key = "case/evidence.mp4"
        asset.sha256_hash = sha

        storage = MagicMock()
        storage.get_object_stream.return_value = (
            len(payload),
            iter([payload]),
        )

        with (
            patch(
                "loom.services.court_bundle.build_court_bundle_data",
                new_callable=AsyncMock,
                return_value=_stub_data(),
            ),
            patch(
                "loom.services.court_bundle._fetch_exhibits",
                new_callable=AsyncMock,
                return_value=[asset],
            ),
        ):
            _, exported = await build_court_bundle(
                session,
                _CASE_ID,
                options={"include_originals": True},
                storage=storage,
                dest_path=dest,
            )

        assert exported == [
            {"id": str(asset.id), "sha256": sha, "exhibit_number": 1}
        ]
        with zipfile.ZipFile(dest) as zf:
            assert zf.read("exhibits/E001_evidence.mp4") == payload
            manifest = zf.read("MANIFEST.sha256").decode("utf-8")
        assert f"{sha}  exhibits/E001_evidence.mp4" in manifest

    @pytest.mark.asyncio
    async def test_refuses_corrupt_original(self, tmp_path: Path) -> None:
        """a stored original that fails re-verification aborts the
        bundle rather than shipping corrupted evidence."""
        session = MagicMock()
        dest = tmp_path / "bundle.zip"

        asset = MagicMock()
        asset.id = uuid4()
        asset.original_filename = "evidence.mp4"
        asset.storage_key = "case/evidence.mp4"
        asset.sha256_hash = "a" * 64

        storage = MagicMock()
        storage.get_object_stream.return_value = (8, iter([b"tampered"]))

        with (
            patch(
                "loom.services.court_bundle.build_court_bundle_data",
                new_callable=AsyncMock,
                return_value=_stub_data(),
            ),
            patch(
                "loom.services.court_bundle._fetch_exhibits",
                new_callable=AsyncMock,
                return_value=[asset],
            ),
            pytest.raises(BundleVerificationError),
        ):
            await build_court_bundle(
                session,
                _CASE_ID,
                options={"include_originals": True},
                storage=storage,
                dest_path=dest,
            )

    @pytest.mark.asyncio
    async def test_inner_file_hashes_are_deterministic_across_runs(
        self, tmp_path: Path
    ) -> None:
        """same inputs → same inner-file hashes. weasyprint pdf
        output is sensitive to build-time font metadata, so we
        force the html-fallback path here (raising ImportError
        inside render_report_pdf) to assert the bundle packaging
        itself is deterministic when the renderer is.
        """
        session = MagicMock()

        stub = _stub_data()
        stub["chain_of_custody"] = []
        stub["exhibits"] = []
        stub["preparer"] = "analyst"

        with (
            patch(
                "loom.services.court_bundle.build_court_bundle_data",
                new_callable=AsyncMock,
                return_value=stub,
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
                dest_path=tmp_path / "1.zip",
            )
            await build_court_bundle(
                session,
                _CASE_ID,
                options={},
                storage=MagicMock(),
                dest_path=tmp_path / "2.zip",
            )

        # compare MANIFEST.sha256 contents from both bundles
        def extract_manifest(path: Path) -> str:
            with zipfile.ZipFile(path) as zf:
                return zf.read("MANIFEST.sha256").decode("utf-8")

        m1 = extract_manifest(tmp_path / "1.zip")
        m2 = extract_manifest(tmp_path / "2.zip")
        assert m1 == m2

    @pytest.mark.asyncio
    async def test_custody_entries_reach_report_pdf(
        self, tmp_path: Path
    ) -> None:
        """custody appendix must be generated with include_custody=True
        so the existing report template emits the table.
        """
        session = MagicMock()

        captured_options: dict[str, object] = {}

        async def fake_report_data(s: object, cid: object, opts: dict) -> dict:
            captured_options.update(opts)
            return _report_stub()

        with (
            patch(
                "loom.services.court_bundle.build_court_bundle_data",
                new_callable=AsyncMock,
                return_value=_stub_data(),
            ),
            patch(
                "loom.services.report.build_report_data",
                side_effect=fake_report_data,
            ),
        ):
            await build_court_bundle(
                session,
                _CASE_ID,
                options={"anything": True, "include_analysis": True},
                storage=MagicMock(),
                dest_path=tmp_path / "k.zip",
            )

        # court bundle always forces custody inclusion
        assert captured_options["include_custody"] is True
        assert captured_options["anything"] is True  # preserves caller opts
