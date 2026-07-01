"""Functional tests for video endpoints."""

import uuid

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_create_video_201(client: AsyncClient) -> None:
    resp = await client.post(
        "/v1/videos",
        json={"title": "Test", "category": "Music"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["title"] == "Test"
    assert data["category"] == "Music"
    assert "video_id" in data
    assert "created_at" in data


@pytest.mark.asyncio
async def test_get_video_200(client: AsyncClient) -> None:
    resp = await client.post("/v1/videos", json={"title": "V"})
    video_id = resp.json()["video_id"]

    resp2 = await client.get(f"/v1/videos/{video_id}")
    assert resp2.status_code == 200
    assert resp2.json()["video_id"] == video_id


@pytest.mark.asyncio
async def test_get_video_404(client: AsyncClient) -> None:
    fake_id = str(uuid.uuid4())
    resp = await client.get(f"/v1/videos/{fake_id}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_create_video_minimal(client: AsyncClient) -> None:
    resp = await client.post("/v1/videos", json={"title": "Minimal"})
    assert resp.status_code == 201
    data = resp.json()
    assert data["category"] is None
    assert data["region"] is None
