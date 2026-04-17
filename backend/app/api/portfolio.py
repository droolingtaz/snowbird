import logging

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select
from typing import Optional

logger = logging.getLogger(__name__)

from app.deps import CurrentUser, DbSession
from app.models.account import AlpacaAccount
from app.models.position import Position
from app.models.snapshot import PortfolioSnapshot
from app.schemas.portfolio import PortfolioSummary, PortfolioHistory, HistoryPoint, AllocationResponse, AllocationItem

router = APIRouter(prefix="/portfolio", tags=["portfolio"])


def _get_account(db, user_id: int, account_id: int) -> AlpacaAccount:
    acct = db.execute(
        select(AlpacaAccount).where(
            AlpacaAccount.id == account_id,
            AlpacaAccount.user_id == user_id,
        )
    ).scalar_one_or_none()
    if not acct:
        raise HTTPException(status_code=404, detail="Account not found")
    return acct


@router.get("/summary", response_model=PortfolioSummary)
def portfolio_summary(account_id: int, current_user: CurrentUser, db: DbSession):
    acct = _get_account(db, current_user.id, account_id)
    try:
        from app.services.alpaca import get_trading_client
        client = get_trading_client(acct)
        alpaca_acct = client.get_account()
        equity = float(alpaca_acct.equity or 0)
        cash = float(alpaca_acct.cash or 0)
        buying_power = float(alpaca_acct.buying_power or 0)
        prev_equity = float(alpaca_acct.last_equity or alpaca_acct.equity or equity)
        today_pl = equity - prev_equity
        today_pl_pct = (today_pl / prev_equity * 100) if prev_equity > 0 else 0.0
        long_mv = float(alpaca_acct.long_market_value or 0)

        positions = db.execute(
            select(Position).where(Position.account_id == account_id)
        ).scalars().all()
        total_cost = sum(float(p.avg_entry_price or 0) * float(p.qty) for p in positions)
        total_pl = equity - cash - total_cost

        return PortfolioSummary(
            equity=round(equity, 4),
            cash=round(cash, 4),
            buying_power=round(buying_power, 4),
            today_pl=round(today_pl, 4),
            today_pl_pct=round(today_pl_pct, 4),
            total_pl=round(total_pl, 4),
            positions_count=len(positions),
        )
    except Exception as exc:
        logger.exception("portfolio_summary failed for account_id=%s", account_id)
        positions = db.execute(
            select(Position).where(Position.account_id == account_id)
        ).scalars().all()
        equity = sum(float(p.market_value or 0) for p in positions)
        return PortfolioSummary(
            equity=round(equity, 4),
            cash=0.0, buying_power=0.0,
            today_pl=0.0, today_pl_pct=0.0, total_pl=0.0,
            positions_count=len(positions),
        )


@router.get("/history", response_model=PortfolioHistory)
def portfolio_history(
    account_id: int,
    period: str = Query("1M"),
    timeframe: str = Query("1D"),
    current_user: CurrentUser = None,
    db: DbSession = None,
):
    _get_account(db, current_user.id, account_id)

    # Try Alpaca portfolio history first
    try:
        from app.models.account import AlpacaAccount as AA
        acct = db.get(AA, account_id)
        from app.services.alpaca import get_trading_client
        from alpaca.trading.requests import GetPortfolioHistoryRequest

        # alpaca-py accepts timeframe as a plain string value
        allowed = {"1Min", "5Min", "15Min", "1H", "1D"}
        tf = timeframe if timeframe in allowed else "1D"

        client = get_trading_client(acct)
        req = GetPortfolioHistoryRequest(period=period, timeframe=tf, extended_hours=False)
        hist = client.get_portfolio_history(filter=req)

        if hist and hist.equity:
            points = []
            for i, eq in enumerate(hist.equity):
                ts = hist.timestamp[i] if hist.timestamp else None
                pnl = hist.profit_loss[i] if hist.profit_loss else 0.0
                if eq is not None:
                    from datetime import datetime
                    date_str = datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d") if ts else str(i)
                    points.append(HistoryPoint(date=date_str, equity=float(eq), pnl=float(pnl or 0)))
            base = float(points[0].equity) if points else 0.0
            return PortfolioHistory(points=points, base_value=base)
    except Exception:
        pass

    # Fallback: use local snapshots
    from datetime import date, timedelta
    period_days = {"1D": 1, "1W": 7, "1M": 30, "3M": 90, "YTD": 365, "1Y": 365, "ALL": 3650}.get(period, 30)
    since = date.today() - timedelta(days=period_days)
    snapshots = db.execute(
        select(PortfolioSnapshot)
        .where(PortfolioSnapshot.account_id == account_id, PortfolioSnapshot.date >= since)
        .order_by(PortfolioSnapshot.date)
    ).scalars().all()

    points = [
        HistoryPoint(date=str(s.date), equity=float(s.equity), pnl=float(s.pnl or 0))
        for s in snapshots
    ]
    base = float(points[0].equity) if points else 0.0
    return PortfolioHistory(points=points, base_value=base)


@router.get("/allocation", response_model=AllocationResponse)
def portfolio_allocation(
    account_id: int,
    by: str = Query("sector"),
    current_user: CurrentUser = None,
    db: DbSession = None,
):
    _get_account(db, current_user.id, account_id)

    positions = db.execute(
        select(Position).where(Position.account_id == account_id)
    ).scalars().all()

    total = sum(float(p.market_value or 0) for p in positions)
    if total == 0:
        return AllocationResponse(items=[], total=0.0)

    from app.models.instrument import Instrument
    from app.models.bucket import Bucket, BucketHolding
    from collections import defaultdict

    buckets_by_symbol: dict[str, str] = {}
    if by == "bucket":
        buckets = db.execute(select(Bucket).where(Bucket.account_id == account_id)).scalars().all()
        for b in buckets:
            for h in b.holdings:
                buckets_by_symbol[h.symbol] = b.name

    grouped: dict[str, float] = defaultdict(float)
    for pos in positions:
        mv = float(pos.market_value or 0)
        if by == "sector":
            inst = db.get(Instrument, pos.symbol)
            label = (inst.sector if inst and inst.sector else "Unknown")
        elif by == "asset_class":
            inst = db.get(Instrument, pos.symbol)
            label = (inst.asset_class if inst and inst.asset_class else "Unknown")
        elif by == "etf_category":
            inst = db.get(Instrument, pos.symbol)
            label = (inst.etf_category if inst and inst.etf_category else "Unknown")
        elif by == "bucket":
            label = buckets_by_symbol.get(pos.symbol, "Unassigned")
        else:
            label = pos.symbol
        grouped[label] += mv

    items = [
        AllocationItem(label=lbl, value=round(val, 4), pct=round(val / total * 100, 4))
        for lbl, val in sorted(grouped.items(), key=lambda x: -x[1])
    ]
    return AllocationResponse(items=items, total=round(total, 4))
