"""Unit tests for ORM models — verify table creation and constraints."""

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from youtube_topk.models.video import Video
from youtube_topk.models.view_event import ViewEvent
from youtube_topk.models.window_aggregate import WindowAggregate


@pytest.mark.asyncio
async def test_create_video(db_session: AsyncSession) -> None:
    video = Video(title="Test Video", category="Music")
    db_session.add(video)
    await db_session.flush()
    assert video.video_id is not None
    assert video.title == "Test Video"
    assert video.category == "Music"


@pytest.mark.asyncio
async def test_video_defaults(db_session: AsyncSession) -> None:
    video = Video(title="Minimal")
    db_session.add(video)
    await db_session.flush()
    assert video.region is None
    assert video.created_at is not None


@pytest.mark.asyncio
async def test_view_event_fk_constraint(db_session: AsyncSession) -> None:
    video = Video(title="V")
    db_session.add(video)
    await db_session.flush()

    event = ViewEvent(
        event_id=uuid.uuid4(),
        video_id=video.video_id,
        viewer_id="user1",
        event_time=video.created_at,
    )
    db_session.add(event)
    await db_session.flush()
    assert event.event_id is not None


@pytest.mark.asyncio
async def test_view_event_bad_fk_raises(db_session: AsyncSession) -> None:
    event = ViewEvent(
        event_id=uuid.uuid4(),
        video_id=uuid.uuid4(),  # nonexistent
        viewer_id="user1",
        event_time=None,  # type: ignore — will fail at DB level
    )
    db_session.add(event)
    with pytest.raises(Exception):
        await db_session.flush()


@pytest.mark.asyncio
async def test_window_aggregate_unique_constraint(db_session: AsyncSession) -> None:
    import datetime

    video = Video(title="V")
    db_session.add(video)
    await db_session.flush()

    ws = datetime.datetime(2026, 6, 30, 12, 0, 0, tzinfo=datetime.UTC)
    we = datetime.datetime(2026, 6, 30, 13, 0, 0, tzinfo=datetime.UTC)

    agg1 = WindowAggregate(video_id=video.video_id, window_start=ws, window_end=we, view_count=5)
    db_session.add(agg1)
    await db_session.flush()

    agg2 = WindowAggregate(video_id=video.video_id, window_start=ws, window_end=we, view_count=3)
    db_session.add(agg2)
    with pytest.raises(Exception):
        await db_session.flush()
