"""Portfolio analytics: TWR, CAGR, Sharpe, drawdown, benchmark."""
from __future__ import annotations

import math
import statistics
from datetime import date, timedelta
from decimal import Decimal
from typing import List, Optional, Tuple

from sqlalchemy.orm import Session
from sqlalchemy import select

from app.models.snapshot import PortfolioSnapshot
from app.models.activity import Activity
from app.schemas.analytics import PerformanceMetrics, BenchmarkPoint, MonthlyReturn
from app.config import settings


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
    db: Session, account_id: int, benchmark_symbol: str, period: str
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
        bars = get_bars_cached(benchmark_symbol, "1Day", str(since), str(date.today()))
    except Exception:
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
