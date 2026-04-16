from fastapi import APIRouter, Query
from sqlalchemy import select
from typing import List, Optional

from app.deps import CurrentUser, DbSession
from app.models.account import AlpacaAccount
from app.schemas.dividends import (
    DividendHistoryItem, DividendForecast, DividendCalendarItem, DividendBySymbol
)
from app.services.dividends import (
    get_dividend_history, get_dividend_forecast,
    get_dividend_calendar, get_dividends_by_symbol,
)

router = APIRouter(prefix="/dividends", tags=["dividends"])


@router.get("/history", response_model=List[DividendHistoryItem])
def dividend_history(
    account_id: int,
    year: Optional[int] = None,
    current_user: CurrentUser = None,
    db: DbSession = None,
):
    return get_dividend_history(db, account_id, year)


@router.get("/calendar", response_model=List[DividendCalendarItem])
def dividend_calendar(
    account_id: int,
    from_date: str = Query(alias="from", default=""),
    to_date: str = Query(alias="to", default=""),
    current_user: CurrentUser = None,
    db: DbSession = None,
):
    from datetime import date, timedelta
    if not from_date:
        from_date = str(date.today())
    if not to_date:
        to_date = str(date.today() + timedelta(days=90))
    return get_dividend_calendar(db, account_id, from_date, to_date)


@router.get("/forecast", response_model=DividendForecast)
def dividend_forecast(
    account_id: int,
    current_user: CurrentUser = None,
    db: DbSession = None,
):
    return get_dividend_forecast(db, account_id)


@router.get("/by-symbol", response_model=List[DividendBySymbol])
def dividends_by_symbol(
    account_id: int,
    current_user: CurrentUser = None,
    db: DbSession = None,
):
    return get_dividends_by_symbol(db, account_id)
