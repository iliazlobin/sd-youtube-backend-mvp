"""Functional test fixtures — SQLite in-memory DB + httpx client."""

import os
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient


@pytest.fixture(scope="session", autouse=True)
def set_test_env() -> None:
    """Force SQLite for functional tests in the sandbox."""
    os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture(loop_scope="function")
async def client() -> AsyncGenerator[AsyncClient, None]:
    from youtube_topk.main import create_app

    app = create_app()
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        async with app.router.lifespan_context(app):
            yield ac
