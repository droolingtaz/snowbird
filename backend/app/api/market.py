from fastapi import APIRouter, Query, HTTPException
from sqlalchemy import select
from typing import List

from app.deps import CurrentUser, DbSession
from app.models.account import AlpacaAccount
from app.schemas.market import AssetSearchResult, QuoteOut, BarsResponse, BarOut, MarketClock
from app.services.market_data import get_quote_cached, get_bars_cached, search_assets, get_market_clock

router = APIRouter(prefix="/market", tags=["market"])


def _get_any_account(db, user_id: int) -> AlpacaAccount | None:
    return db.execute(
        select(AlpacaAccount).where(AlpacaAccount.user_id == user_id, AlpacaAccount.active == True)
    ).scalar_one_or_none()


@router.get("/search", response_model=List[AssetSearchResult])
def search(q: str, current_user: CurrentUser, db: DbSession):
    acct = _get_any_account(db, current_user.id)
    if not acct:
        return []
    results = search_assets(acct, q)
    return [AssetSearchResult(**r) for r in results]


@router.get("/quote", response_model=QuoteOut)
def quote(symbol: str, current_user: CurrentUser, db: DbSession):
    acct = _get_any_account(db, current_user.id)
    if not acct:
        raise HTTPException(status_code=404, detail="No active account configured")
    result = get_quote_cached(acct, symbol.upper())
    if not result:
        raise HTTPException(status_code=404, detail=f"Quote not available for {symbol}")
    return QuoteOut(**result)


@router.get("/bars", response_model=BarsResponse)
def bars(
    symbol: str,
    timeframe: str = Query("1Day"),
    start: str = Query(""),
    end: str = Query(""),
    current_user: CurrentUser = None,
    db: DbSession = None,
):
    from datetime import date, timedelta
    acct = _get_any_account(db, current_user.id)
    if not acct:
        return BarsResponse(symbol=symbol, bars=[])

    if not start:
        start = str(date.today() - timedelta(days=365))
    if not end:
        end = str(date.today())

    raw_bars = get_bars_cached(symbol.upper(), timeframe, start, end, account=acct)
    return BarsResponse(
        symbol=symbol,
        bars=[BarOut(**b) for b in raw_bars],
    )


@router.get("/clock", response_model=MarketClock)
def clock(current_user: CurrentUser, db: DbSession):
    acct = _get_any_account(db, current_user.id)
    if not acct:
        return MarketClock(is_open=False)
    result = get_market_clock(acct)
    return MarketClock(**result)
