from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from youtube_topk.db import get_session
from youtube_topk.schemas.event import AcceptedResponse, BatchViewEventsRequest, ViewEventRequest
from youtube_topk.services import events as event_service

router = APIRouter(prefix="/events", tags=["events"])


@router.post("/view", response_model=AcceptedResponse, status_code=status.HTTP_202_ACCEPTED)
async def ingest_view_event(
    body: ViewEventRequest,
    db: AsyncSession = Depends(get_session),
) -> AcceptedResponse:
    inserted = await event_service.ingest_view_event(db, body)
    await db.commit()
    return AcceptedResponse(status="accepted", count=inserted)


@router.post("/view/batch", response_model=AcceptedResponse, status_code=status.HTTP_202_ACCEPTED)
async def ingest_view_events_batch(
    body: BatchViewEventsRequest,
    db: AsyncSession = Depends(get_session),
) -> AcceptedResponse:
    inserted = await event_service.ingest_view_events_batch(db, body.events)
    await db.commit()
    return AcceptedResponse(status="accepted", count=inserted)
