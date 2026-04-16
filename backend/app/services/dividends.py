"""Dividend tracking and forward projections."""
from __future__ import annotations

from datetime import date, timedelta
from typing import List, Optional
from collections import defaultdict

from sqlalchemy.orm import Session
from sqlalchemy import select

from app.models.activity import Activity
from app.models.position import Position
from app.schemas.dividends import (
    DividendHistoryItem, DividendBySymbol, DividendForecast,
    DividendForecastMonth, DividendCalendarItem,
)


def get_dividend_history(db: Session, account_id: int, year: Optional[int] = None) -> List[DividendHistoryItem]:
    query = select(Activity).where(
        Activity.account_id == account_id,
        Activity.activity_type.in_(["DIV", "DIVCGL", "DIVCGS", "DIVNRA", "DIVTXEX"]),
    )
    if year:
        from sqlalchemy import extract
        query = query.where(extract("year", Activity.date) == year)
    query = query.order_by(Activity.date.desc())
    activities = db.execute(query).scalars().all()

    return [
        DividendHistoryItem(
            symbol=act.symbol or "UNKNOWN",
            date=act.date,
            net_amount=float(act.net_amount) if act.net_amount else 0.0,
            qty=float(act.qty) if act.qty else None,
            price=float(act.price) if act.price else None,
        )
        for act in activities
        if act.date
    ]


def get_dividends_by_symbol(db: Session, account_id: int) -> List[DividendBySymbol]:
    activities = db.execute(
        select(Activity).where(
            Activity.account_id == account_id,
            Activity.activity_type.in_(["DIV", "DIVCGL", "DIVCGS", "DIVNRA", "DIVTXEX"]),
        )
    ).scalars().all()

    positions = db.execute(
        select(Position).where(Position.account_id == account_id)
    ).scalars().all()
    qty_by_symbol = {p.symbol: float(p.qty) for p in positions}

    by_symbol: dict[str, list] = defaultdict(list)
    for act in activities:
        if act.symbol and act.net_amount and act.date:
            by_symbol[act.symbol].append(act)

    results = []
    today = date.today()
    year_start = date(today.year, 1, 1)

    for symbol, acts in by_symbol.items():
        total = sum(float(a.net_amount) for a in acts)
        ytd = sum(float(a.net_amount) for a in acts if a.date and a.date >= year_start)
        current_qty = qty_by_symbol.get(symbol, 0.0)

        # Compute annual DPS from last 12 months
        last_12m = [a for a in acts if a.date and a.date >= today - timedelta(days=365)]
        if last_12m and current_qty > 0:
            total_12m = sum(float(a.net_amount) for a in last_12m)
            annual_dps = total_12m / current_qty
        else:
            annual_dps = None

        # Estimate frequency from payment dates
        dates = sorted([a.date for a in acts if a.date])
        frequency = _estimate_frequency(dates)

        projected_annual = annual_dps * current_qty if annual_dps is not None else None

        results.append(DividendBySymbol(
            symbol=symbol,
            total_received=round(total, 4),
            ytd_received=round(ytd, 4),
            annual_dps=round(annual_dps, 4) if annual_dps else None,
            frequency=frequency,
            projected_annual=round(projected_annual, 4) if projected_annual else None,
            current_qty=current_qty,
        ))
    return sorted(results, key=lambda x: x.total_received, reverse=True)


def _estimate_frequency(dates: List[date]) -> Optional[str]:
    if len(dates) < 2:
        return None
    # Average gap between payments in days
    gaps = [(dates[i+1] - dates[i]).days for i in range(len(dates) - 1)]
    avg_gap = sum(gaps) / len(gaps)
    if avg_gap <= 40:
        return "monthly"
    elif avg_gap <= 100:
        return "quarterly"
    elif avg_gap <= 200:
        return "semi-annual"
    else:
        return "annual"


def get_dividend_forecast(db: Session, account_id: int) -> DividendForecast:
    by_symbol = get_dividends_by_symbol(db, account_id)
    positions = db.execute(
        select(Position).where(Position.account_id == account_id)
    ).scalars().all()

    total_cost = sum(
        float(p.avg_entry_price or 0) * float(p.qty)
        for p in positions
    )
    total_market_value = sum(float(p.market_value or 0) for p in positions)

    freq_payments_per_year = {"monthly": 12, "quarterly": 4, "semi-annual": 2, "annual": 1}

    monthly_income: dict[str, float] = defaultdict(float)
    monthly_symbols: dict[str, list] = defaultdict(list)
    total_annual = 0.0

    today = date.today()
    for item in by_symbol:
        if not item.annual_dps or not item.current_qty:
            continue
        annual = item.annual_dps * item.current_qty
        total_annual += annual
        freq = item.frequency or "quarterly"
        payments_per_year = freq_payments_per_year.get(freq, 4)
        payment_per_period = annual / payments_per_year

        # Project on approximate cadence months
        if freq == "monthly":
            months_offset = list(range(1, 13))
        elif freq == "quarterly":
            months_offset = [3, 6, 9, 12]
        elif freq == "semi-annual":
            months_offset = [6, 12]
        else:
            months_offset = [12]

        for offset in months_offset:
            pay_date = today + timedelta(days=offset * 30)
            month_key = f"{pay_date.year}-{pay_date.month:02d}"
            monthly_income[month_key] += payment_per_period
            monthly_symbols[month_key].append(item.symbol)

    # Build sorted monthly array
    monthly = []
    for key in sorted(monthly_income.keys()):
        monthly.append(DividendForecastMonth(
            month=key,
            projected_income=round(monthly_income[key], 4),
            symbols=list(set(monthly_symbols[key])),
        ))

    yield_on_cost = total_annual / total_cost if total_cost > 0 else None
    forward_yield = total_annual / total_market_value if total_market_value > 0 else None

    return DividendForecast(
        monthly=monthly,
        annual_total=round(total_annual, 4),
        yield_on_cost=round(yield_on_cost, 6) if yield_on_cost else None,
        forward_yield=round(forward_yield, 6) if forward_yield else None,
    )


def get_dividend_calendar(db: Session, account_id: int, from_date: str, to_date: str) -> List[DividendCalendarItem]:
    """Approximate calendar from historical patterns (no external calendar API)."""
    by_symbol = get_dividends_by_symbol(db, account_id)
    positions = db.execute(
        select(Position).where(Position.account_id == account_id)
    ).scalars().all()
    qty_by_symbol = {p.symbol: float(p.qty) for p in positions}

    results = []
    try:
        from_d = date.fromisoformat(from_date)
        to_d = date.fromisoformat(to_date)
    except Exception:
        return []

    for item in by_symbol:
        if not item.annual_dps:
            continue
        freq = item.frequency or "quarterly"
        freq_map = {"monthly": 30, "quarterly": 90, "semi-annual": 180, "annual": 365}
        period_days = freq_map.get(freq, 90)

        current = from_d
        while current <= to_d:
            qty = qty_by_symbol.get(item.symbol, 0.0)
            dps = item.annual_dps / (365 / period_days) if item.annual_dps else 0
            results.append(DividendCalendarItem(
                symbol=item.symbol,
                ex_date=str(current - timedelta(days=5)),
                pay_date=str(current),
                amount_per_share=round(float(dps), 4),
                projected_income=round(float(dps) * qty, 4) if qty else None,
            ))
            current += timedelta(days=period_days)

    return sorted(results, key=lambda x: x.pay_date or "")
