import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from youtube_topk.db import get_session
from youtube_topk.schemas.video import CreateVideoRequest, VideoResponse
from youtube_topk.services import videos as video_service

router = APIRouter(prefix="/videos", tags=["videos"])


@router.post("", response_model=VideoResponse, status_code=status.HTTP_201_CREATED)
async def create_video(
    body: CreateVideoRequest,
    db: AsyncSession = Depends(get_session),
) -> VideoResponse:
    video = await video_service.create_video(db, body)
    await db.commit()
    return VideoResponse.model_validate(video)


@router.get("/{video_id}", response_model=VideoResponse)
async def get_video(
    video_id: uuid.UUID,
    db: AsyncSession = Depends(get_session),
) -> VideoResponse:
    video = await video_service.get_video(db, video_id)
    if video is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Video not found")
    return VideoResponse.model_validate(video)
