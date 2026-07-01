from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from youtube_topk.db import get_session
from youtube_topk.schemas.topk import TopKMetadata, TopKResponse, TopKResult
from youtube_topk.services import aggregation as agg_service

router = APIRouter(prefix="/top-k", tags=["top-k"])


@router.get("", response_model=TopKResponse)
async def get_top_k(
    window: Literal["hour", "day"] = Query(...),
    k: int = Query(default=50, ge=1, le=100),
    db: AsyncSession = Depends(get_session),
) -> TopKResponse:
    try:
        window_start, window_end = agg_service.compute_window_boundaries(window)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid window: {window}. Must be 'hour' or 'day'.",
        )

    results = await agg_service.get_top_k(db, window_start, window_end, k)
    now = datetime.now(timezone.utc)

    top_k_results = [
        TopKResult(
            video_id=row["video_id"],
            title=row["title"],
            view_count=row["view_count"],
            rank=idx + 1,
        )
        for idx, row in enumerate(results)
    ]

    return TopKResponse(
        results=top_k_results,
        metadata=TopKMetadata(window=window, refreshed_at=now, k=k),
    )
