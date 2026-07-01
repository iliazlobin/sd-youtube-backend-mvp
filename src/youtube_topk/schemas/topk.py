from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class TopKResult(BaseModel):
    video_id: UUID
    title: str
    view_count: int
    rank: int


class TopKMetadata(BaseModel):
    window: str
    refreshed_at: datetime
    k: int


class TopKResponse(BaseModel):
    results: list[TopKResult]
    metadata: TopKMetadata
