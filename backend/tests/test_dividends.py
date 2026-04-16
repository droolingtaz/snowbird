"""Dividend history + by-symbol aggregation."""
from decimal import Decimal
from datetime import date, timedelta

from app.models.activity import Activity
from app.models.position import Position
from app.services.dividends import get_dividend_history, get_dividends_by_symbol


def test_dividend_history_filters_to_div_activities(db, demo_account):
    today = date.today()
    db.add_all([
        Activity(account_id=demo_account.id, alpaca_id="a1",
                 activity_type="DIV", symbol="AAPL",
                 net_amount=Decimal("24.00"), date=today - timedelta(days=5)),
        Activity(account_id=demo_account.id, alpaca_id="a2",
                 activity_type="FILL", symbol="AAPL",
                 net_amount=Decimal("-180.00"), date=today - timedelta(days=10)),
        Activity(account_id=demo_account.id, alpaca_id="a3",
                 activity_type="DIV", symbol="MSFT",
                 net_amount=Decimal("18.75"), date=today - timedelta(days=3)),
    ])
    db.commit()

    history = get_dividend_history(db, demo_account.id)
    assert len(history) == 2
    symbols = {h.symbol for h in history}
    assert symbols == {"AAPL", "MSFT"}


def test_dividend_history_year_filter(db, demo_account):
    db.add_all([
        Activity(account_id=demo_account.id, alpaca_id="y1",
                 activity_type="DIV", symbol="AAPL",
                 net_amount=Decimal("10"), date=date(2025, 6, 1)),
        Activity(account_id=demo_account.id, alpaca_id="y2",
                 activity_type="DIV", symbol="AAPL",
                 net_amount=Decimal("10"), date=date(2026, 3, 1)),
    ])
    db.commit()
    hist_2025 = get_dividend_history(db, demo_account.id, year=2025)
    hist_2026 = get_dividend_history(db, demo_account.id, year=2026)
    assert len(hist_2025) == 1
    assert len(hist_2026) == 1


def test_dividends_by_symbol_aggregates(db, demo_account):
    today = date.today()
    # 10 shares of AAPL, 4 quarterly dividends of $6 each = $24 total
    db.add(Position(
        account_id=demo_account.id, symbol="AAPL",
        qty=Decimal("10"), avg_entry_price=Decimal("150"),
        market_value=Decimal("1800"), unrealized_pl=Decimal("0"),
        unrealized_plpc=Decimal("0"), current_price=Decimal("180"),
    ))
    for i, months_ago in enumerate([1, 4, 7, 10]):
        db.add(Activity(
            account_id=demo_account.id, alpaca_id=f"d{i}",
            activity_type="DIV", symbol="AAPL",
            net_amount=Decimal("6"),
            date=today - timedelta(days=months_ago * 30),
        ))
    db.commit()

    rows = get_dividends_by_symbol(db, demo_account.id)
    assert len(rows) == 1
    row = rows[0]
    assert row.symbol == "AAPL"
    # Total dividends: $24
    assert float(row.total_received) == pytest.approx(24.0, abs=0.01)
    assert row.current_qty == pytest.approx(10.0, abs=0.01)


import pytest
