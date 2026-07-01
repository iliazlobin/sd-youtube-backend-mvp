"""Black-box acceptance tests — FR4: Metadata on top-K response."""

import os

import pytest
from httpx import AsyncClient


@pytest.fixture
def api_base() -> str:
    return os.environ.get("API_BASE_URL", "http://localhost:8000")


@pytest.mark.asyncio
async def test_fr4_metadata_present(api_base: str) -> None:
    """FR4: Every GET /v1/top-k response includes metadata with window, refreshed_at, k."""
    async with AsyncClient(base_url=api_base) as client:
        resp = await client.get("/v1/top-k?window=hour&k=10")
        assert resp.status_code == 200
        data = resp.json()
        assert "metadata" in data
        meta = data["metadata"]
        assert "window" in meta
        assert meta["window"] == "hour"
        assert "refreshed_at" in meta
        assert "k" in meta
        assert meta["k"] == 10
