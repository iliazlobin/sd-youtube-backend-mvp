import uuid
from datetime import UTC, datetime

import pytest

from youtube_topk.schemas.event import ViewEventRequest
from youtube_topk.services.events import ingest_view_event, ingest_view_events_batch


@pytest.mark.asyncio
async def test_ingest_single_event(db_session):
    # First create a video
    from youtube_topk.models.video import Video

    vid = uuid.uuid4()
    video = Video(video_id=vid, title="Test", category="music")
    db_session.add(video)
    await db_session.flush()

    event = ViewEventRequest(
        event_id=uuid.uuid4(),
        video_id=vid,
        viewer_id="user1",
        event_time=datetime(2026, 6, 30, 14, 5, 0, tzinfo=UTC),
    )
    inserted = await ingest_view_event(db_session, event)
    assert inserted == 1


@pytest.mark.asyncio
async def test_ingest_idempotency(db_session):
    from youtube_topk.models.video import Video

    vid = uuid.uuid4()
    video = Video(video_id=vid, title="Idempotent", category="sports")
    db_session.add(video)
    await db_session.flush()

    event_id = uuid.uuid4()
    event = ViewEventRequest(
        event_id=event_id,
        video_id=vid,
        viewer_id="user_dup",
        event_time=datetime(2026, 6, 30, 14, 10, 0, tzinfo=UTC),
    )

    # First insert
    first = await ingest_view_event(db_session, event)
    assert first == 1

    # Second insert with same event_id — should be a no-op
    second = await ingest_view_event(db_session, event)
    assert second == 0


@pytest.mark.asyncio
async def test_ingest_batch(db_session):
    from youtube_topk.models.video import Video

    vid = uuid.uuid4()
    video = Video(video_id=vid, title="Batch Test", category="news")
    db_session.add(video)
    await db_session.flush()

    events = [
        ViewEventRequest(
            event_id=uuid.uuid4(),
            video_id=vid,
            viewer_id=f"batch_user_{i}",
            event_time=datetime(2026, 6, 30, 14, i, 0, tzinfo=UTC),
        )
        for i in range(5)
    ]
    inserted = await ingest_view_events_batch(db_session, events)
    assert inserted == 5


@pytest.mark.asyncio
async def test_ingest_batch_with_duplicates(db_session):
    from youtube_topk.models.video import Video

    vid = uuid.uuid4()
    video = Video(video_id=vid, title="Batch Dup", category="entertainment")
    db_session.add(video)
    await db_session.flush()

    event_id_new = uuid.uuid4()
    event_id_dup = uuid.uuid4()

    events = [
        ViewEventRequest(
            event_id=event_id_new,
            video_id=vid,
            viewer_id="new_user",
            event_time=datetime(2026, 6, 30, 14, 0, 0, tzinfo=UTC),
        ),
        ViewEventRequest(
            event_id=event_id_dup,
            video_id=vid,
            viewer_id="dup_user",
            event_time=datetime(2026, 6, 30, 14, 1, 0, tzinfo=UTC),
        ),
    ]

    # First batch — both new
    first = await ingest_view_events_batch(db_session, events)
    assert first == 2

    # Second batch with same event_ids — both should be duplicates
    second = await ingest_view_events_batch(db_session, events)
    assert second == 0

    # Mix of new and duplicate
    mixed = events + [
        ViewEventRequest(
            event_id=uuid.uuid4(),
            video_id=vid,
            viewer_id="mixed_new",
            event_time=datetime(2026, 6, 30, 14, 2, 0, tzinfo=UTC),
        )
    ]
    third = await ingest_view_events_batch(db_session, mixed)
    assert third == 1  # only the new one


@pytest.mark.asyncio
async def test_ingest_empty_batch(db_session):
    inserted = await ingest_view_events_batch(db_session, [])
    assert inserted == 0
