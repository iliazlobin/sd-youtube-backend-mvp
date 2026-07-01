import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from youtube_topk.models.video import Video
from youtube_topk.schemas.video import CreateVideoRequest


async def create_video(db: AsyncSession, data: CreateVideoRequest) -> Video:
    video = Video(
        video_id=uuid.uuid4(),
        title=data.title,
        category=data.category,
        region=data.region,
    )
    db.add(video)
    await db.flush()
    await db.refresh(video)
    return video


async def get_video(db: AsyncSession, video_id: uuid.UUID) -> Video | None:
    result = await db.execute(select(Video).where(Video.video_id == video_id))
    return result.scalar_one_or_none()
