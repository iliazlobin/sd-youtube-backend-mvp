import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from youtube_topk.models.video import Video
from youtube_topk.models.view_event import ViewEvent
from youtube_topk.models.window_aggregate import WindowAggregate


def compute_window_boundaries(
    window: str, reference_time: datetime | None = None
) -> tuple[datetime, datetime]:
    """Compute the most recently completed tumbling window boundaries.

    'hour': floor to current hour, window is the previous completed hour.
    'day':  floor to midnight UTC, window is the previous completed day.
    """
    if reference_time is None:
        reference_time = datetime.now(UTC)

    if window == "hour":
        window_end = reference_time.replace(minute=0, second=0, microsecond=0)
        window_start = window_end - timedelta(hours=1)
    elif window == "day":
        window_end = reference_time.replace(hour=0, minute=0, second=0, microsecond=0)
        window_start = window_end - timedelta(days=1)
    else:
        raise ValueError(f"Unknown window: {window}")

    return window_start, window_end


async def aggregate_window(
    db: AsyncSession, window_start: datetime, window_end: datetime
) -> None:
    """Aggregate view events for a time window into window_aggregates.

    Uses UPSERT (ON CONFLICT DO UPDATE) so re-running is idempotent.
    Works across PostgreSQL and SQLite dialects.
    """
    # Count events per video_id in the window
    count_stmt = (
        select(
            ViewEvent.video_id,
            func.count().label("view_count"),
        )
        .where(
            ViewEvent.event_time >= window_start,
            ViewEvent.event_time < window_end,
        )
        .group_by(ViewEvent.video_id)
    )
    result = await db.execute(count_stmt)
    counts = result.fetchall()

    for video_id, view_count in counts:
        # Normalize video_id: on SQLite it's a string (hex), on PG it's a UUID
        vid_str = video_id.hex if hasattr(video_id, "hex") else str(video_id)
        upsert_stmt = text(
            """
            INSERT INTO window_aggregates (video_id, window_start, window_end, view_count)
            VALUES (:video_id, :window_start, :window_end, :view_count)
            ON CONFLICT (video_id, window_start) DO UPDATE
            SET view_count = window_aggregates.view_count + :view_count,
                window_end = :window_end
            """
        )
        await db.execute(
            upsert_stmt,
            {
                "video_id": vid_str,
                "window_start": window_start,
                "window_end": window_end,
                "view_count": view_count,
            },
        )


async def get_top_k(
    db: AsyncSession, window_start: datetime, window_end: datetime, k: int
) -> list[dict]:
    """Return the top-K videos by view count for a given window."""
    stmt = (
        select(
            WindowAggregate.video_id,
            Video.title,
            WindowAggregate.view_count,
        )
        .join(Video, Video.video_id == WindowAggregate.video_id)
        .where(
            WindowAggregate.window_start == window_start,
            WindowAggregate.window_end == window_end,
        )
        .order_by(WindowAggregate.view_count.desc())
        .limit(k)
    )
    result = await db.execute(stmt)
    rows = result.fetchall()
    return [
        {"video_id": row[0], "title": row[1], "view_count": row[2]}
        for row in rows
    ]


async def get_window_count(
    db: AsyncSession, video_id: uuid.UUID, window_start: datetime
) -> int:
    """Return the view count for a single video in a window."""
    stmt = select(func.coalesce(func.sum(WindowAggregate.view_count), 0)).where(
        WindowAggregate.video_id == video_id,
        WindowAggregate.window_start == window_start,
    )
    result = await db.execute(stmt)
    return result.scalar_one()
