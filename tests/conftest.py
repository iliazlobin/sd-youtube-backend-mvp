"""Unit test fixtures — SQLite in-memory database."""

from collections.abc import AsyncGenerator

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from youtube_topk.models import (
    view_event,  # noqa: F401 — registers table on Base.metadata
    window_aggregate,  # noqa: F401 — registers table on Base.metadata
)
from youtube_topk.models.video import Base


@pytest_asyncio.fixture(loop_scope="function")
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Provide an async SQLAlchemy session backed by in-memory SQLite."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    await engine.dispose()
