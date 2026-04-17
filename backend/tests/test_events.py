"""Tests for the upcoming events service."""
from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import patch

from app.models.position import Position
from app.models.instrument import Instrument
from app.models.activity import Activity
from app.services.events import get_upcoming_events


def test_events_empty_positions(db, demo_account):
    """No positions -> empty events list."""
    result = get_upcoming_events(db, demo_account.id, days=30)
    assert result.events == []


def test_events_dividend_calendar(db, demo_account):
    """Positions with dividend history produce ex-div + payment events."""
    inst = Instrument(symbol="AAPL", name="Apple Inc.")
    db.add(inst)

    pos = Position(
        account_id=demo_account.id, symbol="AAPL",
        qty=10, avg_entry_price=150, market_value=1700, current_price=170,
    )
    db.add(pos)

    today = date.today()
    for i in range(4):
        db.add(Activity(
            account_id=demo_account.id,
            alpaca_id=f"div-aapl-{i}",
            activity_type="DIV",
            symbol="AAPL",
            qty=10,
            price=0.24,
            net_amount=2.40,
            date=today - timedelta(days=90 * (i + 1)),
        ))
    db.commit()

    result = get_upcoming_events(db, demo_account.id, days=120)
    div_events = [e for e in result.events if e.event_type in ("ex_dividend", "dividend_payment")]
    assert len(div_events) > 0
    for e in div_events:
        assert e.symbol == "AAPL"


@patch("app.services.events.get_earnings_for_symbols")
@patch("app.services.events.settings")
def test_events_merged_earnings_and_dividends(mock_settings, mock_earnings, db, demo_account):
    """With Finnhub key set, earnings events are merged with dividend events."""
    mock_settings.FINNHUB_API_KEY = "test-key"

    inst = Instrument(symbol="MSFT", name="Microsoft Corp")
    db.add(inst)
    pos = Position(
        account_id=demo_account.id, symbol="MSFT",
        qty=5, avg_entry_price=300, market_value=1750, current_price=350,
    )
    db.add(pos)

    today = date.today()
    for i in range(4):
        db.add(Activity(
            account_id=demo_account.id,
            alpaca_id=f"div-msft-{i}",
            activity_type="DIV",
            symbol="MSFT",
            qty=5,
            price=0.75,
            net_amount=3.75,
            date=today - timedelta(days=90 * (i + 1)),
        ))
    db.commit()

    tomorrow = str(today + timedelta(days=1))
    mock_earnings.return_value = [
        {"symbol": "MSFT", "date": tomorrow, "epsEstimate": 2.85, "revenueEstimate": 61000000000},
    ]

    result = get_upcoming_events(db, demo_account.id, days=120)
    assert result.has_finnhub is True

    earnings_events = [e for e in result.events if e.event_type == "earnings"]
    assert len(earnings_events) >= 1
    assert earnings_events[0].symbol == "MSFT"
    assert any(d.key == "eps_estimate" for d in earnings_events[0].details)


@patch("app.services.events.settings")
def test_events_graceful_without_finnhub(mock_settings, db, demo_account):
    """Without FINNHUB_API_KEY, only dividend events are returned."""
    mock_settings.FINNHUB_API_KEY = None

    inst = Instrument(symbol="VZ", name="Verizon")
    db.add(inst)
    pos = Position(
        account_id=demo_account.id, symbol="VZ",
        qty=20, avg_entry_price=40, market_value=900, current_price=45,
    )
    db.add(pos)
    today = date.today()
    for i in range(4):
        db.add(Activity(
            account_id=demo_account.id,
            alpaca_id=f"div-vz-{i}",
            activity_type="DIV",
            symbol="VZ",
            qty=20,
            price=0.665,
            net_amount=13.30,
            date=today - timedelta(days=90 * (i + 1)),
        ))
    db.commit()

    result = get_upcoming_events(db, demo_account.id, days=120)
    assert result.has_finnhub is False
    div_events = [e for e in result.events if e.event_type in ("ex_dividend", "dividend_payment")]
    assert len(div_events) > 0
