"""Unit tests for aggregation service — window boundaries + top-K."""

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from youtube_topk.schemas.event import ViewEventRequest
from youtube_topk.schemas.video import CreateVideoRequest
from youtube_topk.services import aggregation as agg_service
from youtube_topk.services import events as event_service
from youtube_topk.services import videos as video_service


def test_compute_window_boundaries_hour() -> None:
    ref = datetime(2026, 6, 30, 14, 35, 0, tzinfo=timezone.utc)
    ws, we = agg_service.compute_window_boundaries("hour", ref)
    assert ws == datetime(2026, 6, 30, 13, 0, 0, tzinfo=timezone.utc)
    assert we == datetime(2026, 6, 30, 14, 0, 0, tzinfo=timezone.utc)


def test_compute_window_boundaries_day() -> None:
    ref = datetime(2026, 6, 30, 14, 35, 0, tzinfo=timezone.utc)
    ws, we = agg_service.compute_window_boundaries("day", ref)
    assert ws == datetime(2026, 6, 29, 0, 0, 0, tzinfo=timezone.utc)
    assert we == datetime(2026, 6, 30, 0, 0, 0, tzinfo=timezone.utc)


def test_compute_window_boundaries_invalid_window() -> None:
    with pytest.raises(ValueError, match="Unknown window"):
        agg_service.compute_window_boundaries("month")


@pytest.mark.asyncio
async def test_aggregate_and_top_k(db_session: AsyncSession) -> None:
    now = datetime(2026, 6, 30, 14, 0, 0, tzinfo=timezone.utc)

    v1 = await video_service.create_video(db_session, CreateVideoRequest(title="V1"))
    v2 = await video_service.create_video(db_session, CreateVideoRequest(title="V2"))
    await db_session.flush()

    # Ingest events in the 13:00-14:00 window
    for i in range(10):
        await event_service.ingest_view_event(
            db_session,
            ViewEventRequest(
                event_id=uuid.uuid4(),
                video_id=v1.video_id,
                viewer_id=f"u{i}",
                event_time=datetime(2026, 6, 30, 13, 30, 0, tzinfo=timezone.utc),
            ),
        )
    for i in range(5):
        await event_service.ingest_view_event(
            db_session,
            ViewEventRequest(
                event_id=uuid.uuid4(),
                video_id=v2.video_id,
                viewer_id=f"u{i+100}",
                event_time=datetime(2026, 6, 30, 13, 45, 0, tzinfo=timezone.utc),
            ),
        )
    await db_session.flush()

    ws, we = agg_service.compute_window_boundaries("hour", now)
    await agg_service.aggregate_window(db_session, ws, we)
    await db_session.flush()

    results = await agg_service.get_top_k(db_session, ws, we, 10)
    assert len(results) == 2
    assert results[0]["video_id"] == v1.video_id
    assert results[0]["view_count"] == 10
    assert results[1]["video_id"] == v2.video_id
    assert results[1]["view_count"] == 5


@pytest.mark.asyncio
async def test_empty_window_returns_empty(db_session: AsyncSession) -> None:
    ws = datetime(2026, 6, 30, 10, 0, 0, tzinfo=timezone.utc)
    we = datetime(2026, 6, 30, 11, 0, 0, tzinfo=timezone.utc)
    results = await agg_service.get_top_k(db_session, ws, we, 10)
    assert results == []


@pytest.mark.asyncio
async def test_upsert_rerun_idempotent(db_session: AsyncSession) -> None:
    now = datetime(2026, 6, 30, 15, 0, 0, tzinfo=timezone.utc)

    v = await video_service.create_video(db_session, CreateVideoRequest(title="V"))
    await db_session.flush()

    await event_service.ingest_view_event(
        db_session,
        ViewEventRequest(
            event_id=uuid.uuid4(),
            video_id=v.video_id,
            viewer_id="u1",
            event_time=datetime(2026, 6, 30, 14, 30, 0, tzinfo=timezone.utc),
        ),
    )
    await db_session.flush()

    ws, we = agg_service.compute_window_boundaries("hour", now)

    # First aggregation
    await agg_service.aggregate_window(db_session, ws, we)
    await db_session.flush()

    results1 = await agg_service.get_top_k(db_session, ws, we, 10)
    assert results1[0]["view_count"] == 1

    # Rerun — should be idempotent (UPSERT)
    await agg_service.aggregate_window(db_session, ws, we)
    await db_session.flush()

    results2 = await agg_service.get_top_k(db_session, ws, we, 10)
    assert results2[0]["view_count"] == 1  # same count, not doubled
