"""View event ingestion with idempotency (ON CONFLICT DO NOTHING)."""


from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from youtube_topk.schemas.event import ViewEventRequest


async def ingest_view_event(db: AsyncSession, event: ViewEventRequest) -> int:
    """Insert a view event idempotently on event_id.

    Returns 1 if the event was inserted, 0 if it was a duplicate.
    """
    stmt = text(
        """
        INSERT INTO view_events (event_id, video_id, viewer_id, event_time)
        VALUES (:event_id, :video_id, :viewer_id, :event_time)
        ON CONFLICT (event_id) DO NOTHING
        """
    )
    result = await db.execute(
        stmt,
        {
            "event_id": event.event_id.hex,
            "video_id": event.video_id.hex,
            "viewer_id": event.viewer_id,
            "event_time": event.event_time,
        },
    )
    return result.rowcount


async def ingest_view_events_batch(db: AsyncSession, events: list[ViewEventRequest]) -> int:
    """Batch insert view events with idempotency. Returns count of new inserts."""
    if not events:
        return 0

    total_inserted = 0
    for event in events:
        inserted = await ingest_view_event(db, event)
        total_inserted += inserted
    return total_inserted
