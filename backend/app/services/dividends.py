"""Dividend tracking and forward projections."""
from __future__ import annotations

import json
import pathlib
from datetime import date, timedelta
from functools import lru_cache
from typing import List, Optional
from collections import defaultdict

from sqlalchemy.orm import Session
from sqlalchemy import select, extract

from app.models.activity import Activity
from app.models.position import Position
from app.schemas.dividends import (
    DividendHistoryItem, DividendBySymbol, DividendForecast,
    DividendForecastMonth, DividendCalendarItem,
    FuturePaymentMonth, FuturePaymentsResponse,
    ReceivedMonth, ReceivedMonthlyResponse,
    GrowthYearMonth, GrowthYear, GrowthYoYResponse,
)

DIV_TYPES = ["DIV", "DIVCGL", "DIVCGS", "DIVNRA", "DIVROC", "DIVTXEX"]

_ETF_JSON = pathlib.Path(__file__).resolve().parent.parent / "data" / "etf_classifications.json"


@lru_cache(maxsize=1)
def _load_curated_dividends() -> dict[str, dict]:
    """Return {symbol: {annual_dps, frequency}} for symbols with curated data."""
    with open(_ETF_JSON) as f:
        data = json.load(f)
    return {
        sym: {"annual_dps": entry["annual_dps"], "frequency": entry["frequency"]}
        for sym, entry in data.items()
        if "annual_dps" in entry and "frequency" in entry
    }


def get_dividend_history(db: Session, account_id: int, year: Optional[int] = None) -> List[DividendHistoryItem]:
    query = select(Activity).where(
        Activity.account_id == account_id,
        Activity.activity_type.in_(DIV_TYPES),
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
            Activity.activity_type.in_(DIV_TYPES),
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

    # Fallback: fill gaps for held symbols with no DIV history using curated data
    symbols_with_history = {r.symbol for r in results}
    curated = _load_curated_dividends()
    for symbol, qty in qty_by_symbol.items():
        if symbol in symbols_with_history or symbol not in curated:
            continue
        meta = curated[symbol]
        annual_dps = meta["annual_dps"]
        projected_annual = annual_dps * qty if qty > 0 else None
        results.append(DividendBySymbol(
            symbol=symbol,
            total_received=0.0,
            ytd_received=0.0,
            annual_dps=annual_dps,
            frequency=meta["frequency"],
            projected_annual=round(projected_annual, 4) if projected_annual else None,
            current_qty=qty,
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


# ── Chart endpoints ──────────────────────────────────────────────────────────

def get_future_payments(db: Session, account_id: int, months: int = 12) -> FuturePaymentsResponse:
    """Aggregate forecasted dividend payments by month for the next N months.

    Uses the existing forecast logic. Payments with an ex-date already in the
    calendar are "confirmed"; the rest are "estimated".
    """
    forecast = get_dividend_forecast(db, account_id)

    today = date.today()
    # Calendar items with an ex_date in the past are "confirmed"
    calendar = get_dividend_calendar(
        db, account_id,
        from_date=str(today),
        to_date=str(today + timedelta(days=months * 31)),
    )
    confirmed_keys: set[tuple[str, str]] = set()
    for item in calendar:
        if item.ex_date:
            try:
                ex = date.fromisoformat(item.ex_date)
                if ex <= today:
                    pay_month = item.pay_date[:7] if item.pay_date else None
                    if pay_month:
                        confirmed_keys.add((item.symbol, pay_month))
            except Exception:
                pass

    # Build month buckets from forecast monthly data
    monthly_confirmed: dict[str, float] = defaultdict(float)
    monthly_estimated: dict[str, float] = defaultdict(float)

    for fm in forecast.monthly:
        for sym in fm.symbols:
            per_sym = fm.projected_income / len(fm.symbols) if fm.symbols else 0
            if (sym, fm.month) in confirmed_keys:
                monthly_confirmed[fm.month] += per_sym
            else:
                monthly_estimated[fm.month] += per_sym

    # Collect all months and sort
    all_months = sorted(set(monthly_confirmed.keys()) | set(monthly_estimated.keys()))[:months]

    result_months = []
    for m in all_months:
        c = round(monthly_confirmed.get(m, 0.0), 2)
        e = round(monthly_estimated.get(m, 0.0), 2)
        result_months.append(FuturePaymentMonth(
            month=m, confirmed=c, estimated=e, total=round(c + e, 2),
        ))

    return FuturePaymentsResponse(months=result_months)


def get_received_monthly(db: Session, account_id: int, months: int = 12) -> ReceivedMonthlyResponse:
    """Aggregate actual dividend receipts by month for trailing N months."""
    cutoff = date.today() - timedelta(days=months * 31)

    activities = db.execute(
        select(Activity).where(
            Activity.account_id == account_id,
            Activity.activity_type.in_(DIV_TYPES),
            Activity.date >= cutoff,
        ).order_by(Activity.date)
    ).scalars().all()

    by_month: dict[str, float] = defaultdict(float)
    for act in activities:
        if act.date and act.net_amount:
            key = f"{act.date.year}-{act.date.month:02d}"
            by_month[key] += float(act.net_amount)

    result_months = [
        ReceivedMonth(month=k, total=round(v, 2))
        for k, v in sorted(by_month.items())
    ]
    return ReceivedMonthlyResponse(months=result_months)


def get_growth_yoy(db: Session, account_id: int, years: int = 3) -> GrowthYoYResponse:
    """Monthly dividend totals for the current year and N-1 prior years."""
    today = date.today()
    start_year = today.year - (years - 1)
    cutoff = date(start_year, 1, 1)

    activities = db.execute(
        select(Activity).where(
            Activity.account_id == account_id,
            Activity.activity_type.in_(DIV_TYPES),
            Activity.date >= cutoff,
        ).order_by(Activity.date)
    ).scalars().all()

    # year -> month -> total
    grid: dict[int, dict[int, float]] = defaultdict(lambda: defaultdict(float))
    for act in activities:
        if act.date and act.net_amount:
            grid[act.date.year][act.date.month] += float(act.net_amount)

    result_years = []
    for yr in range(start_year, today.year + 1):
        max_month = today.month if yr == today.year else 12
        months = []
        for m in range(1, max_month + 1):
            months.append(GrowthYearMonth(month=m, total=round(grid[yr].get(m, 0.0), 2)))
        result_years.append(GrowthYear(year=yr, months=months))

    return GrowthYoYResponse(years=result_years)
