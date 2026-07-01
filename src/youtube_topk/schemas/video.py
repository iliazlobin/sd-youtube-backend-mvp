from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class CreateVideoRequest(BaseModel):
    title: str
    category: str | None = None
    region: str | None = None


class VideoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    video_id: UUID
    title: str
    category: str | None
    region: str | None
    created_at: datetime
