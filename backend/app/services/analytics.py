"""Portfolio analytics: TWR, CAGR, Sharpe, drawdown, benchmark, IRR, income, movers."""
from __future__ import annotations

import logging
import math
import statistics
from datetime import date, timedelta
from decimal import Decimal
from typing import List, Optional, Tuple

from sqlalchemy.orm import Session
from sqlalchemy import select, func

from app.models.snapshot import PortfolioSnapshot
from app.models.activity import Activity
from app.models.position import Position
from app.models.instrument import Instrument
from app.schemas.analytics import (
    PerformanceMetrics, BenchmarkPoint, MonthlyReturn,
    IrrResponse, PassiveIncomeResponse, MoverItem, MoversResponse,
)
from app.config import settings

logger = logging.getLogger(__name__)


def _period_to_days(period: str) -> int:
    mapping = {
        "1D": 1, "1W": 7, "1M": 30, "3M": 90,
        "YTD": (date.today() - date(date.today().year, 1, 1)).days + 1,
        "1Y": 365, "ALL": 10 * 365,
    }
    return mapping.get(period, 365)


def get_snapshots(db: Session, account_id: int, days: int) -> List[PortfolioSnapshot]:
    since = date.today() - timedelta(days=days)
    return db.execute(
        select(PortfolioSnapshot)
        .where(PortfolioSnapshot.account_id == account_id, PortfolioSnapshot.date >= since)
        .order_by(PortfolioSnapshot.date)
    ).scalars().all()


def compute_daily_returns(snapshots: List[PortfolioSnapshot], db: Session, account_id: int) -> List[float]:
    """Compute chain-linked daily returns with cash-flow adjustments."""
    if len(snapshots) < 2:
        return []

    # Fetch net flows (deposits/withdrawals) keyed by date
    activities = db.execute(
        select(Activity).where(
            Activity.account_id == account_id,
            Activity.activity_type.in_(["JNLC", "JNLS", "ACH", "PTC", "CSD", "CSW"]),
        )
    ).scalars().all()

    flows_by_date: dict[date, float] = {}
    for act in activities:
        if act.date and act.net_amount:
            d = act.date
            flows_by_date[d] = flows_by_date.get(d, 0.0) + float(act.net_amount)

    returns = []
    for i in range(1, len(snapshots)):
        prev = snapshots[i - 1]
        curr = snapshots[i]
        prev_equity = float(prev.equity)
        curr_equity = float(curr.equity)
        net_flow = flows_by_date.get(curr.date, 0.0)
        if prev_equity <= 0:
            continue
        r = (curr_equity - prev_equity - net_flow) / prev_equity
        returns.append(r)

    return returns


def compute_performance(db: Session, account_id: int, period: str = "1Y") -> PerformanceMetrics:
    days = _period_to_days(period)
    snapshots = get_snapshots(db, account_id, days)

    if len(snapshots) < 2:
        return PerformanceMetrics(days=len(snapshots))

    daily_returns = compute_daily_returns(snapshots, db, account_id)
    if not daily_returns:
        return PerformanceMetrics(days=len(snapshots))

    # TWR
    twr = 1.0
    for r in daily_returns:
        twr *= (1 + r)
    twr -= 1.0

    # CAGR
    actual_days = max((snapshots[-1].date - snapshots[0].date).days, 1)
    cagr = (1 + twr) ** (365.0 / actual_days) - 1 if actual_days > 0 else None

    # Volatility
    try:
        vol = statistics.stdev(daily_returns) * math.sqrt(252) if len(daily_returns) >= 2 else None
    except Exception:
        vol = None

    # Sharpe
    rf = settings.RISK_FREE_RATE
    if vol and vol > 0:
        mean_daily = sum(daily_returns) / len(daily_returns)
        sharpe = (mean_daily * 252 - rf) / vol
    else:
        sharpe = None

    # Max drawdown
    equities = [float(s.equity) for s in snapshots]
    peak = equities[0]
    max_dd = 0.0
    for eq in equities:
        if eq > peak:
            peak = eq
        dd = eq / peak - 1 if peak > 0 else 0
        if dd < max_dd:
            max_dd = dd

    best_day = max(daily_returns) if daily_returns else None
    worst_day = min(daily_returns) if daily_returns else None

    start_equity = float(snapshots[0].equity)
    end_equity = float(snapshots[-1].equity)
    total_return_pct = (end_equity - start_equity) / start_equity if start_equity > 0 else None

    return PerformanceMetrics(
        twr=round(twr, 6),
        cagr=round(cagr, 6) if cagr is not None else None,
        total_return_pct=round(total_return_pct, 6) if total_return_pct is not None else None,
        volatility=round(vol, 6) if vol is not None else None,
        sharpe=round(sharpe, 4) if sharpe is not None else None,
        max_drawdown=round(max_dd, 6),
        best_day=round(best_day, 6) if best_day is not None else None,
        worst_day=round(worst_day, 6) if worst_day is not None else None,
        days=len(snapshots),
    )


def compute_monthly_returns(db: Session, account_id: int) -> List[MonthlyReturn]:
    snapshots = db.execute(
        select(PortfolioSnapshot)
        .where(PortfolioSnapshot.account_id == account_id)
        .order_by(PortfolioSnapshot.date)
    ).scalars().all()

    if not snapshots:
        return []

    # Group snapshots by year-month, take first and last
    months: dict[Tuple[int, int], list] = {}
    for s in snapshots:
        key = (s.date.year, s.date.month)
        months.setdefault(key, []).append(s)

    results = []
    for (year, month), snaps in sorted(months.items()):
        if len(snaps) >= 2:
            start_eq = float(snaps[0].equity)
            end_eq = float(snaps[-1].equity)
            ret = (end_eq - start_eq) / start_eq if start_eq > 0 else None
            results.append(MonthlyReturn(year=year, month=month, return_pct=round(ret, 6) if ret is not None else None))
        else:
            results.append(MonthlyReturn(year=year, month=month, return_pct=None))
    return results


def compute_benchmark(
    db: Session, account_id: int, benchmark_symbol: str, period: str, account=None
) -> Tuple[List[BenchmarkPoint], Optional[float], Optional[float]]:
    """Compute portfolio vs benchmark normalized series."""
    from app.services.market_data import get_bars_cached

    days = _period_to_days(period)
    since = date.today() - timedelta(days=days)
    snapshots = get_snapshots(db, account_id, days)

    if not snapshots:
        return [], None, None

    # Fetch benchmark bars
    try:
        bars = get_bars_cached(benchmark_symbol, "1Day", str(since), str(date.today()), account=account)
    except Exception as exc:
        logger.warning("Benchmark bars fetch failed for %s: %s", benchmark_symbol, exc)
        bars = []

    if not bars:
        return [], None, None

    # Build date lookup for snapshots
    snap_by_date = {s.date: float(s.equity) for s in snapshots}
    bar_by_date = {b["timestamp"][:10]: b["close"] for b in bars}

    # Intersect dates
    common_dates = sorted(set(snap_by_date.keys()) & {date.fromisoformat(d) for d in bar_by_date.keys()})
    if not common_dates:
        return [], None, None

    port_base = snap_by_date[common_dates[0]]
    bench_base = bar_by_date[str(common_dates[0])]

    if port_base == 0 or bench_base == 0:
        return [], None, None

    points = []
    for d in common_dates:
        port_val = snap_by_date.get(d)
        bench_val = bar_by_date.get(str(d))
        if port_val is not None and bench_val is not None:
            points.append(BenchmarkPoint(
                date=str(d),
                portfolio=round(port_val / port_base * 100, 4),
                benchmark=round(bench_val / bench_base * 100, 4),
            ))

    port_ret = (snap_by_date[common_dates[-1]] / port_base - 1) if port_base > 0 else None
    bench_ret = (bar_by_date[str(common_dates[-1])] / bench_base - 1) if bench_base > 0 else None

    return points, port_ret, bench_ret


# ── IRR ───────────────────────────────────────────────────────────────────────

CASHFLOW_TYPES = ["JNLC", "JNLS", "CSD", "CSW", "ACH", "PTC"]


def compute_irr(db: Session, account_id: int, period: str = "1Y") -> IrrResponse:
    """Compute internal rate of return from cashflows and snapshots."""
    import pyxirr

    days = _period_to_days(period)
    snapshots = get_snapshots(db, account_id, days)
    today = date.today()

    if len(snapshots) < 2:
        return IrrResponse(period=period, irr=None, as_of=str(today))

    initial_equity = float(snapshots[0].equity)
    final_equity = float(snapshots[-1].equity)
    start_date = snapshots[0].date

    # Build cashflow array: Day 0 = outflow (initial investment)
    dates_list: list[date] = [start_date]
    amounts: list[float] = [-initial_equity]

    # Add deposits (JNLC/CSD/ACH in) as outflows and withdrawals as inflows
    activities = db.execute(
        select(Activity).where(
            Activity.account_id == account_id,
            Activity.activity_type.in_(CASHFLOW_TYPES),
            Activity.date >= start_date,
        ).order_by(Activity.date)
    ).scalars().all()

    for act in activities:
        if not act.date or not act.net_amount:
            continue
        net = float(act.net_amount)
        dates_list.append(act.date)
        amounts.append(-net)

    # Final day: current equity as inflow
    dates_list.append(today)
    amounts.append(final_equity)

    try:
        irr_val = pyxirr.xirr(dates_list, amounts)
        if irr_val is not None and math.isfinite(irr_val):
            irr_val = round(irr_val, 6)
        else:
            irr_val = None
    except Exception:
        irr_val = None

    return IrrResponse(period=period, irr=irr_val, as_of=str(today))


# ── Passive Income ────────────────────────────────────────────────────────────

DIV_TYPES = ["DIV", "DIVCGL", "DIVCGS", "DIVNRA", "DIVTXEX"]


def compute_passive_income(db: Session, account_id: int) -> PassiveIncomeResponse:
    """Forward 12-month dividend projection and current yield."""
    from app.services.dividends import get_dividend_forecast

    forecast = get_dividend_forecast(db, account_id)
    annual_income = forecast.annual_total
    monthly_income = round(annual_income / 12, 2) if annual_income else 0.0
    current_yield_pct = round(forecast.forward_yield * 100, 2) if forecast.forward_yield else None

    today = date.today()
    one_year_ago = today - timedelta(days=365)
    two_years_ago = today - timedelta(days=730)

    trailing_12m = db.execute(
        select(func.coalesce(func.sum(Activity.net_amount), 0)).where(
            Activity.account_id == account_id,
            Activity.activity_type.in_(DIV_TYPES),
            Activity.date >= one_year_ago,
        )
    ).scalar() or 0

    prior_12m = db.execute(
        select(func.coalesce(func.sum(Activity.net_amount), 0)).where(
            Activity.account_id == account_id,
            Activity.activity_type.in_(DIV_TYPES),
            Activity.date >= two_years_ago,
            Activity.date < one_year_ago,
        )
    ).scalar() or 0

    trailing_12m = float(trailing_12m)
    prior_12m = float(prior_12m)

    if prior_12m > 0:
        yoy_growth_pct = round(((trailing_12m - prior_12m) / prior_12m) * 100, 2)
    else:
        yoy_growth_pct = None

    return PassiveIncomeResponse(
        annual_income=round(annual_income, 2),
        monthly_income=monthly_income,
        current_yield_pct=current_yield_pct,
        yoy_growth_pct=yoy_growth_pct,
    )


# ── Movers ────────────────────────────────────────────────────────────────────

def compute_movers(db: Session, account_id: int, account, limit: int = 5) -> MoversResponse:
    """Today's top gainers and losers by $ change."""
    from app.services.market_data import get_quote_cached

    positions = db.execute(
        select(Position).where(Position.account_id == account_id)
    ).scalars().all()

    if not positions:
        return MoversResponse()

    symbols = [p.symbol for p in positions]
    instruments = db.execute(
        select(Instrument).where(Instrument.symbol.in_(symbols))
    ).scalars().all()
    name_map = {i.symbol: i.name for i in instruments}

    items: list[MoverItem] = []
    for pos in positions:
        symbol = pos.symbol
        qty = float(pos.qty) if pos.qty else 0
        if qty == 0:
            continue

        current_price = float(pos.current_price) if pos.current_price else None
        market_value = float(pos.market_value) if pos.market_value else None

        change_pct = None
        change_usd = None
        try:
            quote = get_quote_cached(account, symbol)
            if quote and quote.get("last_price"):
                live_price = quote["last_price"]
                if current_price and current_price != live_price:
                    change_pct = ((live_price - current_price) / current_price) * 100
                    change_usd = (live_price - current_price) * qty
                    market_value = live_price * qty
        except Exception:
            pass

        if change_pct is None and pos.unrealized_plpc is not None:
            change_pct = round(float(pos.unrealized_plpc) * 100, 2)
            change_usd = float(pos.unrealized_pl) if pos.unrealized_pl else None

        items.append(MoverItem(
            symbol=symbol,
            name=name_map.get(symbol),
            value=round(market_value, 2) if market_value else None,
            change_pct=round(change_pct, 2) if change_pct is not None else None,
            change_usd=round(change_usd, 2) if change_usd is not None else None,
        ))

    items.sort(key=lambda x: abs(x.change_usd) if x.change_usd is not None else 0, reverse=True)

    gainers = [i for i in items if (i.change_usd or 0) > 0][:limit]
    losers = [i for i in items if (i.change_usd or 0) < 0][:limit]

    return MoversResponse(gainers=gainers, losers=losers)
