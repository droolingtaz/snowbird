"""Upcoming events: merges Finnhub earnings + dividend calendar."""
from __future__ import annotations

from datetime import date, timedelta
from typing import List

from sqlalchemy.orm import Session
from sqlalchemy import select

from app.config import settings
from app.models.position import Position
from app.models.instrument import Instrument
from app.schemas.events import UpcomingEvent, UpcomingEventsResponse, EventDetail
from app.services.dividends import get_dividend_calendar
from app.services.finnhub import get_earnings_for_symbols


def get_upcoming_events(
    db: Session, account_id: int, days: int = 30
) -> UpcomingEventsResponse:
    """Merge earnings + dividend events for the next N days."""
    today = date.today()
    to_date = today + timedelta(days=days)

    positions = db.execute(
        select(Position).where(Position.account_id == account_id)
    ).scalars().all()

    if not positions:
        return UpcomingEventsResponse(events=[], has_finnhub=bool(settings.FINNHUB_API_KEY))

    symbols = [p.symbol for p in positions]
    instruments = db.execute(
        select(Instrument).where(Instrument.symbol.in_(symbols))
    ).scalars().all()
    name_map = {i.symbol: i.name for i in instruments}

    events: List[UpcomingEvent] = []

    has_finnhub = bool(settings.FINNHUB_API_KEY)
    if has_finnhub:
        earnings = get_earnings_for_symbols(symbols, today, to_date)
        for e in earnings:
            sym = e.get("symbol", "")
            details: list[EventDetail] = []
            if e.get("epsEstimate") is not None:
                details.append(EventDetail(
                    key="eps_estimate", label="EPS Estimate",
                    value=str(e["epsEstimate"]),
                ))
            if e.get("revenueEstimate") is not None:
                rev = e["revenueEstimate"]
                details.append(EventDetail(
                    key="rev_estimate", label="Revenue Estimate",
                    value=f"${rev:,.0f}" if isinstance(rev, (int, float)) else str(rev),
                ))
            events.append(UpcomingEvent(
                date=e.get("date", str(today)),
                symbol=sym,
                name=name_map.get(sym),
                event_type="earnings",
                description=f"{sym} earnings call",
                details=details,
            ))

    div_items = get_dividend_calendar(db, account_id, str(today), str(to_date))
    for d in div_items:
        if d.ex_date:
            events.append(UpcomingEvent(
                date=d.ex_date,
                symbol=d.symbol,
                name=name_map.get(d.symbol),
                event_type="ex_dividend",
                description=f"{d.symbol} ex-dividend date",
                details=[
                    EventDetail(key="amount", label="Amount/Share",
                                value=f"${d.amount_per_share:.4f}" if d.amount_per_share else None),
                ],
            ))
        if d.pay_date:
            events.append(UpcomingEvent(
                date=d.pay_date,
                symbol=d.symbol,
                name=name_map.get(d.symbol),
                event_type="dividend_payment",
                description=f"{d.symbol} dividend payment",
                details=[
                    EventDetail(key="projected", label="Projected Income",
                                value=f"${d.projected_income:.2f}" if d.projected_income else None),
                ],
            ))

    events.sort(key=lambda e: e.date)
    return UpcomingEventsResponse(events=events, has_finnhub=has_finnhub)
