"""tests for export service functions."""

import hashlib
import json
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest

from loom.models.export_bundle import ExportBundle
from loom.services.export import (
    build_export_manifest,
    create_export_record,
    get_export,
    list_exports,
    package_export_bundle,
)
from loom.services.portable_bundle import BundleVerificationError
from loom.services.storage_backends import ORIGINALS_BUCKET
from loom.services.storage_backends.local import LocalStorageBackend

_CASE_ID = "01912345-6789-7abc-8def-0123456789ef"
_USER_ID = "01912345-6789-7abc-8def-012345678901"
_EXPORT_ID = "01912345-6789-7abc-8def-0123456789ab"
_NOW = datetime(2025, 6, 1, 12, 0, 0, tzinfo=UTC)


class TestCreateExportRecord:
    """create_export_record persists a record."""

    async def test_creates_pending_export(self) -> None:
        """creates export with pending status."""
        session = AsyncMock()
        session.add = MagicMock()

        await create_export_record(
            session, _CASE_ID, "test export", "zip", _USER_ID
        )

        session.add.assert_called_once()
        session.commit.assert_awaited_once()
        session.refresh.assert_awaited_once()
        added = session.add.call_args[0][0]
        assert isinstance(added, ExportBundle)
        assert added.status == "pending"
        assert added.name == "test export"
        assert added.format == "zip"
        assert added.case_id == UUID(_CASE_ID)
        assert added.created_by == UUID(_USER_ID)
        assert added.options is None

    async def test_persists_submitted_options(self) -> None:
        """the export request survives on the record verbatim."""
        session = AsyncMock()
        session.add = MagicMock()

        options = {
            "include_originals": True,
            "include_analysis": False,
            "event_ids": ["e1"],
        }
        await create_export_record(
            session, _CASE_ID, "n", "zip", _USER_ID, options=options
        )

        added = session.add.call_args[0][0]
        assert added.options == options


class TestListExports:
    """list_exports with pagination."""

    async def test_returns_exports_and_total(self) -> None:
        """returns list and count."""
        export = MagicMock(spec=ExportBundle)
        export.id = UUID(_EXPORT_ID)

        session = AsyncMock()
        call_count = 0

        async def mock_execute(query: object) -> MagicMock:
            nonlocal call_count
            call_count += 1
            m = MagicMock()
            if call_count == 1:
                m.scalar_one.return_value = 1
            else:
                m.scalars.return_value.all.return_value = [export]
            return m

        session.execute = AsyncMock(side_effect=mock_execute)

        exports, total = await list_exports(session, _CASE_ID)
        assert total == 1
        assert len(exports) == 1

    async def test_pagination_params(self) -> None:
        """skip/limit params are respected."""
        session = AsyncMock()
        call_count = 0

        async def mock_execute(query: object) -> MagicMock:
            nonlocal call_count
            call_count += 1
            m = MagicMock()
            if call_count == 1:
                m.scalar_one.return_value = 5
            else:
                m.scalars.return_value.all.return_value = []
            return m

        session.execute = AsyncMock(side_effect=mock_execute)

        exports, total = await list_exports(session, _CASE_ID, skip=2, limit=2)
        assert total == 5
        assert exports == []


class TestGetExport:
    """get_export retrieves by id."""

    async def test_returns_export(self) -> None:
        """returns export when found."""
        export = MagicMock(spec=ExportBundle)

        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = export
        session.execute = AsyncMock(return_value=mock_result)

        result = await get_export(session, _EXPORT_ID)
        assert result is export

    async def test_returns_none_when_missing(self) -> None:
        """returns None when export not found."""
        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=mock_result)

        result = await get_export(session, _EXPORT_ID)
        assert result is None


class TestBuildExportManifest:
    """build_export_manifest gathers case data."""

    async def test_gathers_all_data(self) -> None:
        """manifest contains assets, events, annotations, custody."""
        asset = MagicMock()
        asset.id = UUID("00000000-0000-0000-0000-000000000001")
        asset.original_filename = "vid.mp4"
        asset.media_type = "video"
        asset.mime_type = "video/mp4"
        asset.file_size_bytes = 1024
        asset.sha256_hash = "a" * 64
        asset.storage_key = "originals/vid.mp4"

        event = MagicMock()
        event.id = UUID("00000000-0000-0000-0000-000000000002")
        event.title = "Event 1"
        event.description = "desc"
        event.event_time_start = _NOW
        event.event_time_end = None
        event.status = "draft"

        annotation = MagicMock()
        annotation.id = UUID("00000000-0000-0000-0000-000000000003")
        annotation.asset_id = asset.id
        annotation.type = "observation"
        annotation.content = "test note"

        custody = MagicMock()
        custody.id = UUID("00000000-0000-0000-0000-000000000004")
        custody.asset_id = asset.id
        custody.action = "uploaded"
        custody.actor_id = UUID(_USER_ID)
        custody.timestamp = _NOW

        session = AsyncMock()
        call_count = 0

        async def mock_execute(query: object) -> MagicMock:
            nonlocal call_count
            call_count += 1
            m = MagicMock()
            if call_count == 1:
                # assets
                m.scalars.return_value.all.return_value = [asset]
            elif call_count == 2:
                # events
                m.scalars.return_value.all.return_value = [event]
            elif call_count == 3:
                # annotations
                m.scalars.return_value.all.return_value = [annotation]
            elif call_count == 4:
                # custody
                m.scalars.return_value.all.return_value = [custody]
            return m

        session.execute = AsyncMock(side_effect=mock_execute)

        manifest = await build_export_manifest(session, _CASE_ID, {})

        assert manifest["case_id"] == _CASE_ID
        assert len(manifest["assets"]) == 1
        assert manifest["assets"][0]["original_filename"] == "vid.mp4"
        assert len(manifest["timeline_events"]) == 1
        assert len(manifest["annotations"]) == 1
        assert len(manifest["chain_of_custody"]) == 1
        assert manifest["include_originals"] is False

    async def test_respects_options(self) -> None:
        """options filter assets and events."""
        session = AsyncMock()
        call_count = 0

        async def mock_execute(query: object) -> MagicMock:
            nonlocal call_count
            call_count += 1
            m = MagicMock()
            m.scalars.return_value.all.return_value = []
            return m

        session.execute = AsyncMock(side_effect=mock_execute)

        manifest = await build_export_manifest(
            session,
            _CASE_ID,
            {
                "include_originals": True,
                "date_range_start": "2025-01-01T00:00:00",
                "date_range_end": "2025-12-31T23:59:59",
            },
        )

        assert manifest["include_originals"] is True

    async def test_no_custody_when_no_assets(self) -> None:
        """chain of custody empty when no assets."""
        session = AsyncMock()
        call_count = 0

        async def mock_execute(query: object) -> MagicMock:
            nonlocal call_count
            call_count += 1
            m = MagicMock()
            m.scalars.return_value.all.return_value = []
            return m

        session.execute = AsyncMock(side_effect=mock_execute)

        manifest = await build_export_manifest(session, _CASE_ID, {})

        # only 3 queries executed (assets, events, annotations)
        # no custody query since asset list is empty
        assert manifest["chain_of_custody"] == []

    async def test_analysis_layer_excluded_when_opted_out(self) -> None:
        """include_analysis=False skips the work-product queries and
        records the exclusion in the contents section."""
        session = AsyncMock()
        call_count = 0

        async def mock_execute(query: object) -> MagicMock:
            nonlocal call_count
            call_count += 1
            m = MagicMock()
            m.scalars.return_value.all.return_value = []
            return m

        session.execute = AsyncMock(side_effect=mock_execute)

        manifest = await build_export_manifest(
            session, _CASE_ID, {"include_analysis": False}
        )

        # only the assets query ran — events and annotations were
        # never gathered, not gathered-then-dropped
        assert call_count == 1
        assert manifest["timeline_events"] == []
        assert manifest["annotations"] == []
        assert manifest["include_analysis"] is False
        excluded = manifest["contents"]["excluded"]
        assert "timeline_events" in excluded
        assert "annotations" in excluded
        assert "work product" in excluded["timeline_events"]

    async def test_contents_section_counts_included_layers(self) -> None:
        """the manifest states what shipped and what did not."""
        session = AsyncMock()

        async def mock_execute(query: object) -> MagicMock:
            m = MagicMock()
            m.scalars.return_value.all.return_value = []
            return m

        session.execute = AsyncMock(side_effect=mock_execute)

        manifest = await build_export_manifest(session, _CASE_ID, {})

        included = manifest["contents"]["included"]
        assert included["assets"] == 0
        assert included["timeline_events"] == 0
        assert included["annotations"] == 0
        assert manifest["contents"]["excluded"] == {
            "original_files": "not requested"
        }


def _manifest_fixture(**overrides: object) -> dict:
    manifest: dict = {
        "case_id": _CASE_ID,
        "assets": [
            {
                "id": "00000000-0000-0000-0000-000000000001",
                "sha256_hash": "a" * 64,
                "original_filename": "vid.mp4",
                "storage_key": "case/vid.mp4",
            },
        ],
        "timeline_events": [{"id": "1", "title": "E1"}],
        "annotations": [{"id": "2", "content": "note"}],
        "chain_of_custody": [{"id": "3", "action": "uploaded"}],
        "include_originals": False,
        "include_analysis": True,
        "contents": {"included": {"assets": 1}, "excluded": {}},
    }
    manifest.update(overrides)
    return manifest


class TestPackageExportBundle:
    """package_export_bundle writes the zip to disk."""

    def test_creates_zip_with_all_files(self, tmp_path: Path) -> None:
        """zip contains manifest, readme, timeline, etc."""
        manifest = _manifest_fixture()
        storage = LocalStorageBackend(tmp_path, signing_secret="x" * 32)
        dest = tmp_path / "bundle.zip"

        sha256, exported = package_export_bundle(manifest, storage, dest)

        assert len(sha256) == 64
        assert exported == []
        assert sha256 == hashlib.sha256(dest.read_bytes()).hexdigest()

        with zipfile.ZipFile(dest) as zf:
            names = zf.namelist()
            assert "manifest.json" in names
            assert "README.txt" in names
            assert "timeline.json" in names
            assert "annotations.json" in names
            assert "chain_of_custody.json" in names
            assert "checksums.sha256" in names

            m = json.loads(zf.read("manifest.json"))
            assert m["case_id"] == _CASE_ID

    def test_analysis_files_absent_when_excluded(self, tmp_path: Path) -> None:
        """an excluded layer is absent, not shipped as empty files."""
        manifest = _manifest_fixture(
            include_analysis=False,
            timeline_events=[],
            annotations=[],
        )
        storage = LocalStorageBackend(tmp_path, signing_secret="x" * 32)
        dest = tmp_path / "bundle.zip"

        package_export_bundle(manifest, storage, dest)

        with zipfile.ZipFile(dest) as zf:
            names = zf.namelist()
            assert "timeline.json" not in names
            assert "annotations.json" not in names
            # evidence layer still ships
            assert "chain_of_custody.json" in names

    def test_readme_lists_included_and_excluded(self, tmp_path: Path) -> None:
        manifest = _manifest_fixture(
            contents={
                "included": {"assets": 1},
                "excluded": {"original_files": "not requested"},
            }
        )
        storage = LocalStorageBackend(tmp_path, signing_secret="x" * 32)
        dest = tmp_path / "bundle.zip"

        package_export_bundle(manifest, storage, dest)

        with zipfile.ZipFile(dest) as zf:
            readme = zf.read("README.txt").decode("utf-8")
        assert "Included:" in readme
        assert "assets: 1" in readme
        assert "Excluded:" in readme
        assert "original_files: not requested" in readme

    def test_streams_and_verifies_originals(self, tmp_path: Path) -> None:
        """originals are re-hashed on the way into the zip."""
        payload = b"original evidence bytes"
        sha = hashlib.sha256(payload).hexdigest()
        storage = LocalStorageBackend(tmp_path, signing_secret="x" * 32)
        storage.upload_bytes(
            ORIGINALS_BUCKET, "case/vid.mp4", payload, "video/mp4"
        )
        manifest = _manifest_fixture(include_originals=True)
        manifest["assets"][0]["sha256_hash"] = sha
        dest = tmp_path / "bundle.zip"

        _, exported = package_export_bundle(manifest, storage, dest)

        assert exported == [
            {
                "id": "00000000-0000-0000-0000-000000000001",
                "sha256": sha,
            }
        ]
        with zipfile.ZipFile(dest) as zf:
            entry = "evidence/00000000-0000-0000-0000-000000000001/vid.mp4"
            assert zf.read(entry) == payload

    def test_refuses_corrupt_original(self, tmp_path: Path) -> None:
        """a stored file that no longer matches its ingest hash
        aborts the export instead of shipping silently."""
        storage = LocalStorageBackend(tmp_path, signing_secret="x" * 32)
        storage.upload_bytes(
            ORIGINALS_BUCKET, "case/vid.mp4", b"tampered", "video/mp4"
        )
        manifest = _manifest_fixture(include_originals=True)
        dest = tmp_path / "bundle.zip"

        with pytest.raises(BundleVerificationError):
            package_export_bundle(manifest, storage, dest)

    def test_sha256_is_deterministic_shape(self, tmp_path: Path) -> None:
        """hash is the zip file's own sha256."""
        manifest = _manifest_fixture(
            assets=[], timeline_events=[], annotations=[]
        )
        manifest["chain_of_custody"] = []
        storage = LocalStorageBackend(tmp_path, signing_secret="x" * 32)

        h1, _ = package_export_bundle(manifest, storage, tmp_path / "1.zip")
        h2, _ = package_export_bundle(manifest, storage, tmp_path / "2.zip")
        assert len(h1) == 64
        assert len(h2) == 64
        assert len(h2) == 64
