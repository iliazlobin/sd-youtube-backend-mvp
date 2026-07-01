"""Unit tests for video service."""

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from youtube_topk.schemas.video import CreateVideoRequest
from youtube_topk.services import videos as video_service


@pytest.mark.asyncio
async def test_create_video(db_session: AsyncSession) -> None:
    req = CreateVideoRequest(title="Test", category="Cat", region="US")
    video = await video_service.create_video(db_session, req)
    await db_session.flush()
    assert video.video_id is not None
    assert video.title == "Test"
    assert video.category == "Cat"
    assert video.region == "US"


@pytest.mark.asyncio
async def test_get_video_found(db_session: AsyncSession) -> None:
    req = CreateVideoRequest(title="Find me")
    created = await video_service.create_video(db_session, req)
    await db_session.flush()

    found = await video_service.get_video(db_session, created.video_id)
    assert found is not None
    assert found.title == "Find me"


@pytest.mark.asyncio
async def test_get_video_not_found(db_session: AsyncSession) -> None:
    result = await video_service.get_video(db_session, uuid.uuid4())
    assert result is None
