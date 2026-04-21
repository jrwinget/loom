import hashlib
import io
import zipfile
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from loom.services.court_bundle import (
    _compute_manifest,
    build_court_bundle,
)


class TestComputeManifest:
    def test_lines_are_sorted_and_deterministic(self) -> None:
        files = {
            "b.pdf": b"second",
            "a.pdf": b"first",
            "c.pdf": b"third",
        }
        manifest = _compute_manifest(files)
        # lines sorted by path so two runs produce identical output
        lines = manifest.strip().split("\n")
        paths = [line.split("  ")[1] for line in lines]
        assert paths == ["a.pdf", "b.pdf", "c.pdf"]

    def test_hashes_match_file_bytes(self) -> None:
        content = b"hello world"
        manifest = _compute_manifest({"greet.txt": content})
        expected = hashlib.sha256(content).hexdigest()
        assert expected in manifest

    def test_trailing_newline_present(self) -> None:
        # sha256sum-compatible format has a trailing newline
        manifest = _compute_manifest({"x.txt": b""})
        assert manifest.endswith("\n")


class TestBuildCourtBundle:
    @pytest.mark.asyncio
    async def test_bundle_contains_required_files_and_manifest_matches(
        self,
    ) -> None:
        """integration-ish smoke: unzip bundle, verify manifest hashes
        match each file's actual bytes, and the required file set is
        present.
        """
        session = MagicMock()

        # stub both data-building steps — we're testing packaging
        # here, not the sql shape.
        stub_data = {
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

        captured_uploads: dict[str, bytes] = {}

        class StubStorage:
            def upload_bytes(self, bucket, key, data, mime):
                captured_uploads[key] = data

        with (
            patch(
                "loom.services.court_bundle.build_court_bundle_data",
                new_callable=AsyncMock,
                return_value=stub_data,
            ),
            patch(
                "loom.services.report.build_report_data",
                new_callable=AsyncMock,
                return_value=stub_data,
            ),
        ):
            key, sha256 = await build_court_bundle(
                session,
                "01912345-6789-7abc-8def-012345678999",
                options={},
                storage=StubStorage(),
                output_key="exports/bundle.zip",
                preparer="analyst@example.org",
            )

        assert key == "exports/bundle.zip"
        assert len(sha256) == 64

        zip_bytes = captured_uploads[key]
        assert hashlib.sha256(zip_bytes).hexdigest() == sha256

        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            names = set(zf.namelist())
            assert {
                "cover.pdf",
                "report.pdf",
                "exhibit_index.pdf",
                "MANIFEST.sha256",
            }.issubset(names)

            manifest = zf.read("MANIFEST.sha256").decode("utf-8")
            for line in manifest.strip().splitlines():
                digest, path = line.split("  ", 1)
                file_bytes = zf.read(path)
                assert hashlib.sha256(file_bytes).hexdigest() == digest, (
                    f"manifest hash mismatch for {path}"
                )

    @pytest.mark.asyncio
    async def test_inner_file_hashes_are_deterministic_across_runs(
        self,
    ) -> None:
        """same inputs → same inner-file hashes. weasyprint pdf
        output is sensitive to build-time font metadata, so we
        force the html-fallback path here (raising ImportError
        inside render_report_pdf) to assert the bundle packaging
        itself is deterministic when the renderer is.
        """
        session = MagicMock()

        stub_data = {
            "case": {"name": "Test Case", "description": None},
            "events": [],
            "annotations": [],
            "chain_of_custody": [],
            "exhibits": [],
            "preparer": "analyst",
            "generated_at": "2026-04-20T13:00:00+00:00",
            "date_range_start": None,
            "date_range_end": None,
        }

        class Cap(dict):
            def upload_bytes(self, bucket, key, data, mime):
                self[key] = data

        storage_1: Cap = Cap()
        storage_2: Cap = Cap()

        with (
            patch(
                "loom.services.court_bundle.build_court_bundle_data",
                new_callable=AsyncMock,
                return_value=stub_data,
            ),
            patch(
                "loom.services.report.build_report_data",
                new_callable=AsyncMock,
                return_value=stub_data,
            ),
            patch(
                "loom.services.court_bundle.render_report_pdf",
                side_effect=ImportError("forced html fallback"),
            ),
        ):
            await build_court_bundle(
                session,
                "01912345-6789-7abc-8def-012345678999",
                options={},
                storage=storage_1,
                output_key="exports/1.zip",
            )
            await build_court_bundle(
                session,
                "01912345-6789-7abc-8def-012345678999",
                options={},
                storage=storage_2,
                output_key="exports/2.zip",
            )

        # compare MANIFEST.sha256 contents from both bundles
        def extract_manifest(data: bytes) -> str:
            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                return zf.read("MANIFEST.sha256").decode("utf-8")

        m1 = extract_manifest(storage_1["exports/1.zip"])
        m2 = extract_manifest(storage_2["exports/2.zip"])
        assert m1 == m2

    @pytest.mark.asyncio
    async def test_custody_entries_reach_report_pdf(self) -> None:
        """custody appendix must be generated with include_custody=True
        so the existing report template emits the table.
        """
        session = MagicMock()

        captured_options: dict[str, object] = {}

        async def fake_report_data(s, cid, opts):
            captured_options.update(opts)
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

        with (
            patch(
                "loom.services.court_bundle.build_court_bundle_data",
                new_callable=AsyncMock,
                return_value={
                    "case": {"name": "C", "description": None},
                    "events": [],
                    "annotations": [],
                    "chain_of_custody": [],
                    "exhibits": [],
                    "preparer": "a",
                    "generated_at": "2026-04-20T13:00:00+00:00",
                    "date_range_start": None,
                    "date_range_end": None,
                },
            ),
            patch(
                "loom.services.report.build_report_data",
                side_effect=fake_report_data,
            ),
        ):

            class Storage:
                def upload_bytes(self, b, k, d, m):
                    pass

            await build_court_bundle(
                session,
                "01912345-6789-7abc-8def-012345678999",
                options={"anything": True},
                storage=Storage(),
                output_key="k",
            )

        # court bundle always forces custody inclusion
        assert captured_options["include_custody"] is True
        assert captured_options["anything"] is True  # preserves caller opts
