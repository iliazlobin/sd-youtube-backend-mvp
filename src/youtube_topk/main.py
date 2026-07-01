from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from youtube_topk import db
from youtube_topk.config import Settings
from youtube_topk.routers import events, health, topk, videos


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = Settings()
    await db.init_db(settings)

    # Create tables for SQLite dev convenience; production uses Alembic
    from youtube_topk.models import view_event  # noqa: F401
    from youtube_topk.models import window_aggregate  # noqa: F401
    from youtube_topk.models.video import Base

    async with db._engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield
    await db.close_db()


def create_app() -> FastAPI:
    app = FastAPI(title="YouTube Top-K Leaderboard MVP", version="0.1.0", lifespan=lifespan)

    app.include_router(health.router)
    app.include_router(videos.router, prefix="/v1")
    app.include_router(events.router, prefix="/v1")
    app.include_router(topk.router, prefix="/v1")

    return app


app = create_app()
