from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from youtube_topk.config import Settings
from youtube_topk.db import close_db, init_db
from youtube_topk.routers import events, health, topk, videos


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = Settings()
    await init_db(settings)
    yield
    await close_db()


def create_app() -> FastAPI:
    app = FastAPI(title="YouTube Top-K Leaderboard MVP", version="0.1.0", lifespan=lifespan)

    app.include_router(health.router)
    app.include_router(videos.router, prefix="/v1")
    app.include_router(events.router, prefix="/v1")
    app.include_router(topk.router, prefix="/v1")

    return app


app = create_app()
