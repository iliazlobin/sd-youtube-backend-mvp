"""Functional tests for event endpoints."""

import uuid

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_ingest_single_202(client: AsyncClient) -> None:
    # Create a video first
    v_resp = await client.post("/v1/videos", json={"title": "V"})
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
    assert data["count"] == 1


@pytest.mark.asyncio
async def test_ingest_batch_202(client: AsyncClient) -> None:
    v_resp = await client.post("/v1/videos", json={"title": "V"})
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
    assert resp.json()["count"] == 3


@pytest.mark.asyncio
async def test_batch_over_500_rejected(client: AsyncClient) -> None:
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
async def test_missing_fields_422(client: AsyncClient) -> None:
    resp = await client.post("/v1/events/view", json={"video_id": str(uuid.uuid4())})
    assert resp.status_code == 422
