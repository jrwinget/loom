"""tests for clustering service functions."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest
from fastapi import HTTPException

from loom.models.event_cluster import EventCluster, EventClusterItem
from loom.models.timeline import TimelineEvent
from loom.services.clustering import (
    accept_cluster,
    compute_absolute_times,
    get_cluster,
    list_clusters,
    merge_clusters,
    propose_clusters,
    reject_cluster,
)

_CASE_ID = "01912345-6789-7abc-8def-0123456789ef"
_USER_ID = "01912345-6789-7abc-8def-012345678901"
_ASSET_A = UUID("00000000-0000-0000-0000-000000000001")
_ASSET_B = UUID("00000000-0000-0000-0000-000000000002")
_CLUSTER_ID = "01912345-6789-7abc-8def-0123456789cc"
_BASE = datetime(2025, 6, 1, 12, 0, 0, tzinfo=UTC)


def _mock_asset(
    asset_id: UUID,
    capture_time: datetime,
    filename: str = "test.mp4",
) -> MagicMock:
    """build a mock asset."""
    asset = MagicMock()
    asset.id = asset_id
    asset.capture_time = capture_time
    asset.original_filename = filename
    return asset


def _mock_segment(
    seg_id: UUID,
    start: float,
    end: float,
    text: str = "hello",
) -> MagicMock:
    """build a mock transcript segment."""
    seg = MagicMock()
    seg.id = seg_id
    seg.start_time = start
    seg.end_time = end
    seg.text = text
    return seg


def _mock_ocr_region(
    region_id: UUID,
    timestamp: float,
    text: str = "sign",
) -> MagicMock:
    """build a mock ocr region."""
    r = MagicMock()
    r.id = region_id
    r.timestamp = timestamp
    r.text = text
    return r


def _mock_annotation(
    ann_id: UUID,
    time_start: float,
    time_end: float | None = None,
    content: str = "note",
) -> MagicMock:
    """build a mock annotation."""
    a = MagicMock()
    a.id = ann_id
    a.time_start = time_start
    a.time_end = time_end
    a.content = content
    return a


class TestComputeAbsoluteTimes:
    """compute_absolute_times with mocked session."""

    async def test_returns_empty_when_no_assets(self) -> None:
        """returns empty list when no assets have capture_time."""
        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        session.execute = AsyncMock(return_value=mock_result)

        items = await compute_absolute_times(session, _CASE_ID)
        assert items == []

    async def test_maps_transcript_segments(self) -> None:
        """transcript segments get absolute times from asset capture_time."""
        asset = _mock_asset(_ASSET_A, _BASE)
        seg = _mock_segment(
            UUID("10000000-0000-0000-0000-000000000001"),
            10.0,
            20.0,
            "hello world",
        )

        session = AsyncMock()
        # assets query
        asset_result = MagicMock()
        asset_result.scalars.return_value.all.return_value = [asset]
        # segments query
        seg_result = MagicMock()
        seg_result.scalars.return_value.all.return_value = [seg]
        # ocr query (empty)
        ocr_result = MagicMock()
        ocr_result.scalars.return_value.all.return_value = []
        # annotations query (empty)
        ann_result = MagicMock()
        ann_result.scalars.return_value.all.return_value = []

        session.execute = AsyncMock(
            side_effect=[asset_result, seg_result, ocr_result, ann_result]
        )

        items = await compute_absolute_times(session, _CASE_ID)
        assert len(items) == 1
        assert items[0]["content_type"] == "transcript"
        assert items[0]["absolute_time_start"] == _BASE + timedelta(seconds=10)
        assert items[0]["absolute_time_end"] == _BASE + timedelta(seconds=20)
        assert items[0]["text_preview"] == "hello world"

    async def test_maps_ocr_regions(self) -> None:
        """ocr regions get absolute times."""
        asset = _mock_asset(_ASSET_A, _BASE)
        region = _mock_ocr_region(
            UUID("20000000-0000-0000-0000-000000000001"), 5.0, "stop"
        )

        session = AsyncMock()
        asset_result = MagicMock()
        asset_result.scalars.return_value.all.return_value = [asset]
        seg_result = MagicMock()
        seg_result.scalars.return_value.all.return_value = []
        ocr_result = MagicMock()
        ocr_result.scalars.return_value.all.return_value = [region]
        ann_result = MagicMock()
        ann_result.scalars.return_value.all.return_value = []

        session.execute = AsyncMock(
            side_effect=[asset_result, seg_result, ocr_result, ann_result]
        )

        items = await compute_absolute_times(session, _CASE_ID)
        assert len(items) == 1
        assert items[0]["content_type"] == "ocr"
        assert items[0]["absolute_time_start"] == _BASE + timedelta(seconds=5)
        assert items[0]["absolute_time_end"] is None

    async def test_maps_annotations(self) -> None:
        """annotations with time ranges get absolute times."""
        asset = _mock_asset(_ASSET_A, _BASE)
        ann = _mock_annotation(
            UUID("30000000-0000-0000-0000-000000000001"),
            15.0,
            25.0,
            "observation",
        )

        session = AsyncMock()
        asset_result = MagicMock()
        asset_result.scalars.return_value.all.return_value = [asset]
        seg_result = MagicMock()
        seg_result.scalars.return_value.all.return_value = []
        ocr_result = MagicMock()
        ocr_result.scalars.return_value.all.return_value = []
        ann_result = MagicMock()
        ann_result.scalars.return_value.all.return_value = [ann]

        session.execute = AsyncMock(
            side_effect=[asset_result, seg_result, ocr_result, ann_result]
        )

        items = await compute_absolute_times(session, _CASE_ID)
        assert len(items) == 1
        assert items[0]["content_type"] == "annotation"
        assert items[0]["absolute_time_end"] == _BASE + timedelta(seconds=25)

    async def test_annotation_without_time_end(self) -> None:
        """annotation with no time_end maps end to None."""
        asset = _mock_asset(_ASSET_A, _BASE)
        ann = _mock_annotation(
            UUID("30000000-0000-0000-0000-000000000002"),
            15.0,
            None,
            "note",
        )

        session = AsyncMock()
        asset_result = MagicMock()
        asset_result.scalars.return_value.all.return_value = [asset]
        seg_result = MagicMock()
        seg_result.scalars.return_value.all.return_value = []
        ocr_result = MagicMock()
        ocr_result.scalars.return_value.all.return_value = []
        ann_result = MagicMock()
        ann_result.scalars.return_value.all.return_value = [ann]

        session.execute = AsyncMock(
            side_effect=[asset_result, seg_result, ocr_result, ann_result]
        )

        items = await compute_absolute_times(session, _CASE_ID)
        assert len(items) == 1
        assert items[0]["absolute_time_end"] is None


class TestProposeClusters:
    """propose_clusters end-to-end with mocked session."""

    async def test_returns_empty_when_no_items(self) -> None:
        """no assets means no clusters proposed."""
        session = AsyncMock()
        # compute_absolute_times returns empty
        asset_result = MagicMock()
        asset_result.scalars.return_value.all.return_value = []
        session.execute = AsyncMock(return_value=asset_result)

        result = await propose_clusters(session, _CASE_ID, 60, _USER_ID)
        assert result == []

    async def test_creates_clusters_from_overlapping_items(
        self,
    ) -> None:
        """overlapping items from 2 assets produce a cluster."""
        asset_a = _mock_asset(_ASSET_A, _BASE, "cam1.mp4")
        asset_b = _mock_asset(_ASSET_B, _BASE, "cam2.mp4")
        seg_a = _mock_segment(
            UUID("10000000-0000-0000-0000-000000000001"),
            0.0,
            10.0,
            "hello",
        )
        seg_b = _mock_segment(
            UUID("10000000-0000-0000-0000-000000000002"),
            5.0,
            15.0,
            "world",
        )

        fake_cluster_id = UUID(_CLUSTER_ID)
        session = AsyncMock()
        call_count = 0

        async def mock_execute(query: object) -> MagicMock:
            nonlocal call_count
            call_count += 1
            m = MagicMock()
            if call_count == 1:
                # assets with capture_time
                m.scalars.return_value.all.return_value = [
                    asset_a,
                    asset_b,
                ]
            elif call_count == 2:
                # segments for asset_a
                m.scalars.return_value.all.return_value = [seg_a]
            elif call_count == 3:
                # segments for asset_b
                m.scalars.return_value.all.return_value = [seg_b]
            elif call_count <= 7:
                # ocr/annotations (empty)
                m.scalars.return_value.all.return_value = []
            elif call_count == 8:
                # asset_map query
                m.scalars.return_value.all.return_value = [
                    asset_a,
                    asset_b,
                ]
            else:
                # get_cluster calls
                m.scalar_one_or_none.return_value = None
                m.scalars.return_value.all.return_value = []
            return m

        session.execute = AsyncMock(side_effect=mock_execute)

        # assign id when objects are added (simulating db flush)
        def mock_add(obj: object) -> None:
            if isinstance(obj, EventCluster) and obj.id is None:
                obj.id = fake_cluster_id

        session.add = MagicMock(side_effect=mock_add)
        session.flush = AsyncMock()
        session.commit = AsyncMock()

        await propose_clusters(session, _CASE_ID, 60, _USER_ID)
        # session.add should be called (cluster + items)
        assert session.add.call_count >= 1


class TestAcceptCluster:
    """accept_cluster creates timeline event."""

    async def test_sets_status_and_creates_event(self) -> None:
        """accepting creates a timeline event and links it."""
        cluster = MagicMock(spec=EventCluster)
        cluster.id = UUID(_CLUSTER_ID)
        cluster.case_id = UUID(_CASE_ID)
        cluster.time_window_start = _BASE
        cluster.time_window_end = _BASE + timedelta(minutes=5)
        cluster.status = "proposed"

        session = AsyncMock()
        call_count = 0

        async def mock_execute(query: object) -> MagicMock:
            nonlocal call_count
            call_count += 1
            m = MagicMock()
            if call_count == 1:
                # _load_cluster
                m.scalar_one_or_none.return_value = cluster
            elif call_count == 3:
                # get_cluster final load
                m.scalar_one_or_none.return_value = cluster
            else:
                m.scalars.return_value.all.return_value = []
                m.scalar_one_or_none.return_value = cluster
            return m

        session.execute = AsyncMock(side_effect=mock_execute)
        session.add = MagicMock()
        session.flush = AsyncMock()
        session.commit = AsyncMock()
        session.refresh = AsyncMock()

        await accept_cluster(
            session,
            _CLUSTER_ID,
            _CASE_ID,
            "Event Title",
            "desc",
            _USER_ID,
        )

        # a timeline event was added
        added_objects = [c[0][0] for c in session.add.call_args_list]
        assert any(isinstance(o, TimelineEvent) for o in added_objects)
        assert cluster.status == "accepted"


class TestRejectCluster:
    """reject_cluster changes status."""

    async def test_sets_status_to_rejected(self) -> None:
        """rejecting sets status and reviewed_by."""
        cluster = MagicMock(spec=EventCluster)
        cluster.id = UUID(_CLUSTER_ID)
        cluster.case_id = UUID(_CASE_ID)
        cluster.status = "proposed"

        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = cluster
        session.execute = AsyncMock(return_value=mock_result)
        session.commit = AsyncMock()
        session.refresh = AsyncMock()

        await reject_cluster(session, _CLUSTER_ID, _CASE_ID, _USER_ID)
        assert cluster.status == "rejected"
        assert cluster.reviewed_by == UUID(_USER_ID)

    async def test_raises_404_for_missing_cluster(self) -> None:
        """raises HTTPException when cluster not found."""
        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=mock_result)

        with pytest.raises(HTTPException) as exc_info:
            await reject_cluster(session, _CLUSTER_ID, _CASE_ID, _USER_ID)
        assert exc_info.value.status_code == 404


class TestMergeClusters:
    """merge_clusters combines items."""

    async def test_merges_items_into_primary(self) -> None:
        """items from secondary clusters move to primary."""
        cluster1 = MagicMock(spec=EventCluster)
        cluster1.id = UUID("00000000-0000-0000-0000-00000000cc01")
        cluster1.case_id = UUID(_CASE_ID)
        cluster1.status = "proposed"
        cluster1.proposed_title = "Cluster 1"

        cluster2 = MagicMock(spec=EventCluster)
        cluster2.id = UUID("00000000-0000-0000-0000-00000000cc02")
        cluster2.case_id = UUID(_CASE_ID)
        cluster2.status = "proposed"

        item2 = MagicMock(spec=EventClusterItem)
        item2.cluster_id = cluster2.id
        item2.absolute_time_start = _BASE
        item2.absolute_time_end = _BASE + timedelta(minutes=1)

        item1 = MagicMock(spec=EventClusterItem)
        item1.cluster_id = cluster1.id
        item1.absolute_time_start = _BASE - timedelta(minutes=1)
        item1.absolute_time_end = _BASE

        session = AsyncMock()
        call_count = 0

        async def mock_execute(query: object) -> MagicMock:
            nonlocal call_count
            call_count += 1
            m = MagicMock()
            if call_count == 1:
                # _load_cluster for cluster1
                m.scalar_one_or_none.return_value = cluster1
            elif call_count == 2:
                # _load_cluster for cluster2
                m.scalar_one_or_none.return_value = cluster2
            elif call_count == 3:
                # items of cluster2
                m.scalars.return_value.all.return_value = [item2]
            elif call_count == 4:
                # all items of primary after merge
                m.scalars.return_value.all.return_value = [
                    item1,
                    item2,
                ]
            elif call_count == 5:
                # get_cluster
                m.scalar_one_or_none.return_value = cluster1
            else:
                m.scalars.return_value.all.return_value = []
            return m

        session.execute = AsyncMock(side_effect=mock_execute)
        session.commit = AsyncMock()

        await merge_clusters(
            session,
            [str(cluster1.id), str(cluster2.id)],
            _CASE_ID,
            _USER_ID,
        )

        assert cluster2.status == "merged"
        assert item2.cluster_id == cluster1.id


class TestListClusters:
    """list_clusters with status filter."""

    async def test_returns_clusters_and_total(self) -> None:
        """returns paginated clusters with item count."""
        cluster = MagicMock(spec=EventCluster)
        cluster.id = UUID(_CLUSTER_ID)

        session = AsyncMock()
        call_count = 0

        async def mock_execute(query: object) -> MagicMock:
            nonlocal call_count
            call_count += 1
            m = MagicMock()
            if call_count == 1:
                # count query
                m.scalar_one.return_value = 1
            elif call_count == 2:
                # clusters list
                m.scalars.return_value.all.return_value = [cluster]
            else:
                # items for each cluster
                m.scalars.return_value.all.return_value = []
            return m

        session.execute = AsyncMock(side_effect=mock_execute)

        clusters, total = await list_clusters(
            session, _CASE_ID, status="proposed"
        )
        assert total == 1
        assert len(clusters) == 1

    async def test_list_without_filter(self) -> None:
        """returns all clusters when no status filter."""
        session = AsyncMock()
        call_count = 0

        async def mock_execute(query: object) -> MagicMock:
            nonlocal call_count
            call_count += 1
            m = MagicMock()
            if call_count == 1:
                m.scalar_one.return_value = 0
            else:
                m.scalars.return_value.all.return_value = []
            return m

        session.execute = AsyncMock(side_effect=mock_execute)

        clusters, total = await list_clusters(session, _CASE_ID)
        assert total == 0
        assert clusters == []


class TestGetCluster:
    """get_cluster verifies case_id."""

    async def test_returns_cluster_with_items(self) -> None:
        """returns cluster when found with matching case_id."""
        cluster = MagicMock(spec=EventCluster)
        cluster.id = UUID(_CLUSTER_ID)

        session = AsyncMock()
        call_count = 0

        async def mock_execute(query: object) -> MagicMock:
            nonlocal call_count
            call_count += 1
            m = MagicMock()
            if call_count == 1:
                m.scalar_one_or_none.return_value = cluster
            else:
                m.scalars.return_value.all.return_value = []
            return m

        session.execute = AsyncMock(side_effect=mock_execute)

        result = await get_cluster(session, _CLUSTER_ID, _CASE_ID)
        assert result is cluster

    async def test_returns_none_for_wrong_case(self) -> None:
        """returns None when cluster belongs to different case."""
        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=mock_result)

        result = await get_cluster(
            session,
            _CLUSTER_ID,
            "99999999-9999-9999-9999-999999999999",
        )
        assert result is None
