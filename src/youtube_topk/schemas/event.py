from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, field_validator


class ViewEventRequest(BaseModel):
    event_id: UUID
    video_id: UUID
    viewer_id: str
    event_time: datetime


class BatchViewEventsRequest(BaseModel):
    events: list[ViewEventRequest]

    @field_validator("events")
    @classmethod
    def validate_max_events(cls, v: list[ViewEventRequest]) -> list[ViewEventRequest]:
        if len(v) > 500:
            raise ValueError(f"Batch size must not exceed 500, got {len(v)}")
        return v


class AcceptedResponse(BaseModel):
    status: str = "accepted"
    count: int
