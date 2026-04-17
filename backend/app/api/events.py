from fastapi import APIRouter, Query

from app.deps import CurrentUser, DbSession
from app.schemas.events import UpcomingEventsResponse
from app.services.events import get_upcoming_events

router = APIRouter(prefix="/events", tags=["events"])


@router.get("/upcoming", response_model=UpcomingEventsResponse)
def upcoming_events(
    account_id: int,
    days: int = Query(30, ge=1, le=90),
    current_user: CurrentUser = None,
    db: DbSession = None,
):
    return get_upcoming_events(db, account_id, days)
