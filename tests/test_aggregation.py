import uuid
from datetime import UTC, datetime

import pytest

from youtube_topk.services.aggregation import (
    aggregate_window,
    compute_window_boundaries,
    get_top_k,
    get_window_count,
)


class TestComputeWindowBoundaries:
    def test_hour_normal(self):
        ref = datetime(2026, 7, 1, 14, 35, 0, tzinfo=UTC)
        ws, we = compute_window_boundaries("hour", ref)
        assert ws == datetime(2026, 7, 1, 13, 0, 0, tzinfo=UTC)
        assert we == datetime(2026, 7, 1, 14, 0, 0, tzinfo=UTC)

    def test_hour_midnight(self):
        """Edge case: hour=0 should wrap to previous day."""
        ref = datetime(2026, 7, 1, 0, 35, 0, tzinfo=UTC)
        ws, we = compute_window_boundaries("hour", ref)
        assert ws == datetime(2026, 6, 30, 23, 0, 0, tzinfo=UTC)
        assert we == datetime(2026, 7, 1, 0, 0, 0, tzinfo=UTC)

    def test_day_normal(self):
        ref = datetime(2026, 7, 15, 14, 35, 0, tzinfo=UTC)
        ws, we = compute_window_boundaries("day", ref)
        assert ws == datetime(2026, 7, 14, 0, 0, 0, tzinfo=UTC)
        assert we == datetime(2026, 7, 15, 0, 0, 0, tzinfo=UTC)

    def test_day_first_of_month(self):
        """Edge case: day=1 should wrap to previous month."""
        ref = datetime(2026, 7, 1, 14, 35, 0, tzinfo=UTC)
        ws, we = compute_window_boundaries("day", ref)
        assert ws == datetime(2026, 6, 30, 0, 0, 0, tzinfo=UTC)
        assert we == datetime(2026, 7, 1, 0, 0, 0, tzinfo=UTC)

    def test_day_new_year(self):
        """Edge case: day=1 of January wraps to previous year."""
        ref = datetime(2026, 1, 1, 0, 35, 0, tzinfo=UTC)
        ws, we = compute_window_boundaries("day", ref)
        assert ws == datetime(2025, 12, 31, 0, 0, 0, tzinfo=UTC)
        assert we == datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC)

    def test_invalid_window(self):
        with pytest.raises(ValueError):
            compute_window_boundaries("month")

    def test_no_reference_time(self):
        """Should not raise when no reference_time provided."""
        ws, we = compute_window_boundaries("hour")
        assert ws < we
        assert (we - ws).total_seconds() == 3600
        ws2, we2 = compute_window_boundaries("day")
        assert (we2 - ws2).total_seconds() == 86400


class TestAggregationAndTopK:
    @pytest.mark.asyncio
    async def test_aggregate_and_query(self, db_session):
        from youtube_topk.models.video import Video

        vid = uuid.uuid4()
        video = Video(video_id=vid, title="Agg Test", category="music")
        db_session.add(video)
        await db_session.flush()

        # Insert view events directly
        from sqlalchemy import text

        for i in range(3):
            await db_session.execute(
                text(
                    """
                    INSERT INTO view_events (event_id, video_id, viewer_id, event_time)
                    VALUES (:eid, :vid, :uid, :et)
                    ON CONFLICT (event_id) DO NOTHING
                    """
                ),
                {
                    "eid": uuid.uuid4(),
                    "vid": vid,
                    "uid": f"user{i}",
                    "et": datetime(2026, 6, 30, 14, i * 10, 0, tzinfo=UTC),
                },
            )
        await db_session.flush()

        ws = datetime(2026, 6, 30, 14, 0, 0, tzinfo=UTC)
        we = datetime(2026, 6, 30, 15, 0, 0, tzinfo=UTC)

        await aggregate_window(db_session, ws, we)

        results = await get_top_k(db_session, ws, we, k=10)
        assert len(results) == 1
        assert results[0]["video_id"] == vid
        assert results[0]["title"] == "Agg Test"
        assert results[0]["view_count"] == 3

    @pytest.mark.asyncio
    async def test_aggregate_upsert_rerun(self, db_session):
        """Re-running aggregation for the same window accumulates counts."""
        from sqlalchemy import text

        from youtube_topk.models.video import Video

        vid = uuid.uuid4()
        video = Video(video_id=vid, title="Upsert Test", category="gaming")
        db_session.add(video)
        await db_session.flush()

        # Insert 2 events
        for i in range(2):
            await db_session.execute(
                text(
                    """
                    INSERT INTO view_events (event_id, video_id, viewer_id, event_time)
                    VALUES (:eid, :vid, :uid, :et)
                    ON CONFLICT (event_id) DO NOTHING
                    """
                ),
                {
                    "eid": uuid.uuid4(),
                    "vid": vid,
                    "uid": f"user{i}",
                    "et": datetime(2026, 6, 30, 13, i * 30, 0, tzinfo=UTC),
                },
            )
        await db_session.flush()

        ws = datetime(2026, 6, 30, 13, 0, 0, tzinfo=UTC)
        we = datetime(2026, 6, 30, 14, 0, 0, tzinfo=UTC)

        # First aggregation
        await aggregate_window(db_session, ws, we)
        results = await get_top_k(db_session, ws, we, k=10)
        assert results[0]["view_count"] == 2

        # Rerun without new events — adds same count again (idempotent accumulation)
        await aggregate_window(db_session, ws, we)
        results = await get_top_k(db_session, ws, we, k=10)
        assert results[0]["view_count"] == 4

    @pytest.mark.asyncio
    async def test_empty_window(self, db_session):
        """Querying a window with no events returns empty list."""
        ws = datetime(2025, 1, 1, 0, 0, 0, tzinfo=UTC)
        we = datetime(2025, 1, 1, 1, 0, 0, tzinfo=UTC)
        results = await get_top_k(db_session, ws, we, k=10)
        assert results == []

    @pytest.mark.asyncio
    async def test_top_k_limit(self, db_session):
        """Top-K respects the k limit."""
        from sqlalchemy import text

        from youtube_topk.models.video import Video

        videos_data = []
        for i in range(5):
            vid = uuid.uuid4()
            v = Video(video_id=vid, title=f"Video {i}", category="music")
            db_session.add(v)
            videos_data.append(vid)
        await db_session.flush()

        # Insert different counts per video
        ws = datetime(2026, 6, 30, 16, 0, 0, tzinfo=UTC)
        we = datetime(2026, 6, 30, 17, 0, 0, tzinfo=UTC)
        for idx, vid in enumerate(videos_data):
            count = idx + 1  # Video 0 gets 1 view, Video 1 gets 2, etc.
            for _ in range(count):
                await db_session.execute(
                    text(
                        """
                        INSERT INTO view_events (event_id, video_id, viewer_id, event_time)
                        VALUES (:eid, :vid, :uid, :et)
                        ON CONFLICT (event_id) DO NOTHING
                        """
                    ),
                    {
                        "eid": uuid.uuid4(),
                        "vid": vid,
                        "uid": f"user_{idx}_{_}",
                        "et": datetime(2026, 6, 30, 16, idx, 0, tzinfo=UTC),
                    },
                )
        await db_session.flush()

        await aggregate_window(db_session, ws, we)

        # Top 3
        results = await get_top_k(db_session, ws, we, k=3)
        assert len(results) == 3
        # Should be ordered by view_count DESC: Video 4 (5 views), Video 3 (4), Video 2 (3)
        assert results[0]["view_count"] == 5
        assert results[1]["view_count"] == 4
        assert results[2]["view_count"] == 3

    @pytest.mark.asyncio
    async def test_get_window_count(self, db_session):
        from sqlalchemy import text

        from youtube_topk.models.video import Video

        vid = uuid.uuid4()
        video = Video(video_id=vid, title="Count Test", category="news")
        db_session.add(video)
        await db_session.flush()

        ws = datetime(2026, 6, 30, 15, 0, 0, tzinfo=UTC)
        we = datetime(2026, 6, 30, 16, 0, 0, tzinfo=UTC)

        for _ in range(4):
            await db_session.execute(
                text(
                    """
                    INSERT INTO view_events (event_id, video_id, viewer_id, event_time)
                    VALUES (:eid, :vid, :uid, :et)
                    ON CONFLICT (event_id) DO NOTHING
                    """
                ),
                {
                    "eid": uuid.uuid4(),
                    "vid": vid,
                    "uid": f"user{_}",
                    "et": datetime(2026, 6, 30, 15, _, 0, tzinfo=UTC),
                },
            )
        await db_session.flush()
        await aggregate_window(db_session, ws, we)

        count = await get_window_count(db_session, vid, ws)
        assert count == 4

    @pytest.mark.asyncio
    async def test_get_window_count_nonexistent(self, db_session):
        count = await get_window_count(
            db_session, uuid.uuid4(), datetime(2020, 1, 1, 0, 0, 0, tzinfo=UTC)
        )
        assert count == 0
