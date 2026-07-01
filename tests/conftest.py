import os
from collections.abc import AsyncGenerator

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

# Always use PostgreSQL for these white-box tests — never SQLite.
# The functional/conftest.py sets DATABASE_URL to SQLite globally (autouse session fixture),
# so we must use a separate env var or hardcode the PostgreSQL DSN.
PG_TEST_URL = os.environ.get(
    "PG_TEST_DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/youtube_topk_test",
)

_engine = None


def _get_engine():
    global _engine
    if _engine is None:
        _engine = create_async_engine(PG_TEST_URL, echo=False, poolclass=NullPool)
    return _engine


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Provide a fresh async session backed by a new connection each time."""
    engine = _get_engine()
    async with engine.connect() as conn:
        async with conn.begin() as txn:
            session = AsyncSession(bind=conn, expire_on_commit=False)
            yield session
            await txn.rollback()
            await session.close()
