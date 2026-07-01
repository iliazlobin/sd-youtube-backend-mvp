from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from youtube_topk.config import Settings

_engine = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


async def init_db(settings: Settings) -> None:
    global _engine, _sessionmaker
    _engine = create_async_engine(str(settings.DATABASE_URL), echo=False)
    _sessionmaker = async_sessionmaker(_engine, expire_on_commit=False)


async def close_db() -> None:
    global _engine, _sessionmaker
    if _engine:
        await _engine.dispose()
        _engine = None
        _sessionmaker = None


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    if _sessionmaker is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    async with _sessionmaker() as session:
        yield session
