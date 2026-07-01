"""Unit tests for event service — idempotent ingestion."""

import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from youtube_topk.schemas.event import ViewEventRequest
from youtube_topk.schemas.video import CreateVideoRequest
from youtube_topk.services import events as event_service
from youtube_topk.services import videos as video_service


@pytest_asyncio.fixture
async def video_id(db_session: AsyncSession) -> AsyncGenerator[uuid.UUID, None]:
    video = await video_service.create_video(db_session, CreateVideoRequest(title="V"))
    await db_session.flush()
    yield video.video_id


@pytest.fixture
def now() -> datetime:
    return datetime(2026, 6, 30, 12, 0, 0, tzinfo=UTC)


def _make_event(video_id: uuid.UUID, viewer_id: str, event_time: datetime) -> ViewEventRequest:
    return ViewEventRequest(
        event_id=uuid.uuid4(),
        video_id=video_id,
        viewer_id=viewer_id,
        event_time=event_time,
    )


@pytest.mark.asyncio
async def test_single_ingest(db_session: AsyncSession, video_id: uuid.UUID, now: datetime) -> None:
    event = _make_event(video_id, "user1", now)
    count = await event_service.ingest_view_event(db_session, event)
    await db_session.flush()
    assert count == 1


@pytest.mark.asyncio
async def test_idempotency_repost(
    db_session: AsyncSession, video_id: uuid.UUID, now: datetime
) -> None:
    event = _make_event(video_id, "user1", now)
    c1 = await event_service.ingest_view_event(db_session, event)
    await db_session.flush()
    c2 = await event_service.ingest_view_event(db_session, event)
    await db_session.flush()
    assert c1 == 1
    assert c2 == 0


@pytest.mark.asyncio
async def test_batch_ingest(db_session: AsyncSession, video_id: uuid.UUID, now: datetime) -> None:
    events = [_make_event(video_id, f"user{i}", now) for i in range(10)]
    count = await event_service.ingest_view_events_batch(db_session, events)
    await db_session.flush()
    assert count == 10


@pytest.mark.asyncio
async def test_batch_mixed_dup_new(
    db_session: AsyncSession, video_id: uuid.UUID, now: datetime
) -> None:
    new_events = [_make_event(video_id, f"user{i}", now) for i in range(5)]
    c1 = await event_service.ingest_view_events_batch(db_session, new_events)
    await db_session.flush()
    assert c1 == 5

    mixed = list(new_events[:2]) + [_make_event(video_id, f"user{i}", now) for i in range(5, 8)]
    c2 = await event_service.ingest_view_events_batch(db_session, mixed)
    await db_session.flush()
    assert c2 == 3


@pytest.mark.asyncio
async def test_batch_empty(db_session: AsyncSession) -> None:
    count = await event_service.ingest_view_events_batch(db_session, [])
    assert count == 0
