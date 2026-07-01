"""Functional test fixtures — async SQLite test DB + httpx client."""

import asyncio
import os
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session", autouse=True)
def set_test_env():
    os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    from youtube_topk.main import create_app

    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
