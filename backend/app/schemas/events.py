from pydantic import BaseModel
from typing import Optional, List


class EventDetail(BaseModel):
    key: str
    label: str
    value: Optional[str] = None


class UpcomingEvent(BaseModel):
    date: str
    symbol: str
    name: Optional[str] = None
    event_type: str
    description: str
    details: List[EventDetail] = []


class UpcomingEventsResponse(BaseModel):
    events: List[UpcomingEvent] = []
    has_finnhub: bool = False
