import uuid

import pytest

from youtube_topk.schemas.video import CreateVideoRequest
from youtube_topk.services.videos import create_video, get_video


@pytest.mark.asyncio
async def test_create_video(db_session):
    data = CreateVideoRequest(title="Test Video", category="music", region="US")
    video = await create_video(db_session, data)
    await db_session.flush()

    assert video.video_id is not None
    assert isinstance(video.video_id, uuid.UUID)
    assert video.title == "Test Video"
    assert video.category == "music"
    assert video.region == "US"
    assert video.created_at is not None  # server_default populated via refresh


@pytest.mark.asyncio
async def test_get_video_found(db_session):
    data = CreateVideoRequest(title="Find Me", category="gaming")
    created = await create_video(db_session, data)
    await db_session.flush()

    found = await get_video(db_session, created.video_id)
    assert found is not None
    assert found.video_id == created.video_id
    assert found.title == "Find Me"


@pytest.mark.asyncio
async def test_get_video_not_found(db_session):
    result = await get_video(db_session, uuid.uuid4())
    assert result is None
