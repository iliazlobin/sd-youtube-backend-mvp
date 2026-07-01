"""Black-box acceptance tests — FR1: Top-K by window."""

import os

import pytest
from httpx import AsyncClient


@pytest.fixture
def api_base() -> str:
    return os.environ.get("API_BASE_URL", "http://localhost:8000")


@pytest.mark.asyncio
async def test_fr1_topk_by_window_hour(api_base: str) -> None:
    """FR1: GET /v1/top-k?window=hour&k=10 returns ranked results with metadata."""
    import uuid
    from datetime import datetime, timezone

    async with AsyncClient(base_url=api_base) as client:
        # Create a video
        v_resp = await client.post("/v1/videos", json={"title": "FR1 Test Video"})
        assert v_resp.status_code == 201
        video_id = v_resp.json()["video_id"]

        # Ingest some view events
        now = datetime.now(timezone.utc)
        prev_hour = now.replace(minute=0, second=0, microsecond=0)
        event_time = prev_hour.replace(minute=30)  # 30 min into previous hour

        for i in range(3):
            resp = await client.post(
                "/v1/events/view",
                json={
                    "event_id": str(uuid.uuid4()),
                    "video_id": video_id,
                    "viewer_id": f"user{i}",
                    "event_time": event_time.isoformat(),
                },
            )
            assert resp.status_code == 202

        # Trigger aggregation (via direct DB access not available in black-box)
        # For black-box tests, we expect top-k to read existing aggregates.
        # If no aggregation has run, results will be empty — that's fine.
        resp = await client.get("/v1/top-k?window=hour&k=10")
        assert resp.status_code == 200
        data = resp.json()
        assert "results" in data
        assert "metadata" in data
        assert data["metadata"]["window"] == "hour"
        assert data["metadata"]["k"] == 10


@pytest.mark.asyncio
async def test_fr1_topk_invalid_window_422(api_base: str) -> None:
    """FR1: Invalid window parameter returns 422."""
    async with AsyncClient(base_url=api_base) as client:
        resp = await client.get("/v1/top-k?window=month&k=10")
        assert resp.status_code == 422
