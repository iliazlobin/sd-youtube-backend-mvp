"""Functional tests for top-k endpoint."""

import uuid
from datetime import datetime, timezone

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_topk_valid_window_200(client: AsyncClient) -> None:
    resp = await client.get("/v1/top-k?window=hour&k=10")
    assert resp.status_code == 200
    data = resp.json()
    assert "results" in data
    assert "metadata" in data
    assert data["metadata"]["window"] == "hour"
    assert data["metadata"]["k"] == 10


@pytest.mark.asyncio
async def test_topk_invalid_window_422(client: AsyncClient) -> None:
    resp = await client.get("/v1/top-k?window=month&k=10")
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_topk_empty_results(client: AsyncClient) -> None:
    resp = await client.get("/v1/top-k?window=day&k=10")
    assert resp.status_code == 200
    data = resp.json()
    assert data["results"] == []
    assert data["metadata"]["window"] == "day"
