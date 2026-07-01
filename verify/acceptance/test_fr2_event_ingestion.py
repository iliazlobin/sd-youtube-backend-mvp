"""Black-box acceptance tests — FR2: Event ingestion."""

import os
import uuid

import pytest
from httpx import AsyncClient


@pytest.fixture
def api_base() -> str:
    return os.environ.get("API_BASE_URL", "http://localhost:8000")


@pytest.mark.asyncio
async def test_fr2_single_event_202(api_base: str) -> None:
    """FR2: POST /v1/events/view returns 202 Accepted."""
    async with AsyncClient(base_url=api_base) as client:
        v_resp = await client.post("/v1/videos", json={"title": "FR2 Video"})
        video_id = v_resp.json()["video_id"]

        resp = await client.post(
            "/v1/events/view",
            json={
                "event_id": str(uuid.uuid4()),
                "video_id": video_id,
                "viewer_id": "user1",
                "event_time": "2026-06-30T12:00:00Z",
            },
        )
        assert resp.status_code == 202
        data = resp.json()
        assert data["status"] == "accepted"


@pytest.mark.asyncio
async def test_fr2_batch_event_202(api_base: str) -> None:
    """FR2: POST /v1/events/view/batch returns 202 for ≤500 events."""
    async with AsyncClient(base_url=api_base) as client:
        v_resp = await client.post("/v1/videos", json={"title": "FR2 Batch Video"})
        video_id = v_resp.json()["video_id"]

        events = [
            {
                "event_id": str(uuid.uuid4()),
                "video_id": video_id,
                "viewer_id": f"user{i}",
                "event_time": "2026-06-30T12:00:00Z",
            }
            for i in range(3)
        ]
        resp = await client.post("/v1/events/view/batch", json={"events": events})
        assert resp.status_code == 202


@pytest.mark.asyncio
async def test_fr2_batch_over_500_rejected(api_base: str) -> None:
    """FR2: Batch >500 events returns 422."""
    async with AsyncClient(base_url=api_base) as client:
        events = [
            {
                "event_id": str(uuid.uuid4()),
                "video_id": str(uuid.uuid4()),
                "viewer_id": f"user{i}",
                "event_time": "2026-06-30T12:00:00Z",
            }
            for i in range(501)
        ]
        resp = await client.post("/v1/events/view/batch", json={"events": events})
        assert resp.status_code == 422


@pytest.mark.asyncio
async def test_fr2_idempotency(api_base: str) -> None:
    """FR2: Re-posting same event_id is a no-op (202, no error)."""
    async with AsyncClient(base_url=api_base) as client:
        v_resp = await client.post("/v1/videos", json={"title": "FR2 Idempotent"})
        video_id = v_resp.json()["video_id"]

        event_id = str(uuid.uuid4())
        payload = {
            "event_id": event_id,
            "video_id": video_id,
            "viewer_id": "user1",
            "event_time": "2026-06-30T12:00:00Z",
        }

        r1 = await client.post("/v1/events/view", json=payload)
        assert r1.status_code == 202

        r2 = await client.post("/v1/events/view", json=payload)
        assert r2.status_code == 202  # no error on duplicate
