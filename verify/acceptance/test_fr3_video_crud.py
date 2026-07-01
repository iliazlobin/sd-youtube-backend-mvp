"""Black-box acceptance tests — FR3: Video CRUD."""

import os
import uuid

import pytest
from httpx import AsyncClient


@pytest.fixture
def api_base() -> str:
    return os.environ.get("API_BASE_URL", "http://localhost:8000")


@pytest.mark.asyncio
async def test_fr3_create_video_201(api_base: str) -> None:
    """FR3: POST /v1/videos returns 201 with video data."""
    async with AsyncClient(base_url=api_base) as client:
        resp = await client.post(
            "/v1/videos",
            json={"title": "FR3 Test", "category": "Music", "region": "US"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["title"] == "FR3 Test"
        assert data["category"] == "Music"
        assert "video_id" in data
        assert "created_at" in data


@pytest.mark.asyncio
async def test_fr3_get_video_200(api_base: str) -> None:
    """FR3: GET /v1/videos/{id} returns 200 for existing video."""
    async with AsyncClient(base_url=api_base) as client:
        resp = await client.post("/v1/videos", json={"title": "FR3 Get"})
        video_id = resp.json()["video_id"]

        resp2 = await client.get(f"/v1/videos/{video_id}")
        assert resp2.status_code == 200
        assert resp2.json()["video_id"] == video_id


@pytest.mark.asyncio
async def test_fr3_get_video_404(api_base: str) -> None:
    """FR3: GET /v1/videos/{id} returns 404 for nonexistent video."""
    async with AsyncClient(base_url=api_base) as client:
        resp = await client.get(f"/v1/videos/{uuid.uuid4()}")
        assert resp.status_code == 404
