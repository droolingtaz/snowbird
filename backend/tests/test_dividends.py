"""Dividend history, by-symbol aggregation, and chart endpoints."""
from decimal import Decimal
from datetime import date, timedelta

from app.models.activity import Activity
from app.models.position import Position
from app.services.dividends import (
    get_dividend_history, get_dividends_by_symbol, get_dividend_calendar,
    get_future_payments, get_received_monthly, get_growth_yoy,
)


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


# ---------------------------------------------------------------------------
# Received monthly
# ---------------------------------------------------------------------------

def test_received_monthly_aggregates_by_month(db, demo_account):
    """DIV activities are summed by YYYY-MM."""
    db.add_all([
        Activity(account_id=demo_account.id, alpaca_id="rm1",
                 activity_type="DIV", symbol="AAPL",
                 net_amount=Decimal("100.00"), date=date(2026, 1, 15)),
        Activity(account_id=demo_account.id, alpaca_id="rm2",
                 activity_type="DIV", symbol="MSFT",
                 net_amount=Decimal("50.00"), date=date(2026, 1, 28)),
        Activity(account_id=demo_account.id, alpaca_id="rm3",
                 activity_type="DIV", symbol="AAPL",
                 net_amount=Decimal("200.00"), date=date(2026, 2, 10)),
        # Non-DIV should be excluded
        Activity(account_id=demo_account.id, alpaca_id="rm4",
                 activity_type="FILL", symbol="TSLA",
                 net_amount=Decimal("999.00"), date=date(2026, 1, 20)),
    ])
    db.commit()

    result = get_received_monthly(db, demo_account.id, months=24)
    months_dict = {m.month: m.total for m in result.months}
    assert months_dict["2026-01"] == pytest.approx(150.00, abs=0.01)
    assert months_dict["2026-02"] == pytest.approx(200.00, abs=0.01)
    assert "FILL" not in str(result)


def test_received_monthly_empty(db, demo_account):
    """No activities → empty months list."""
    result = get_received_monthly(db, demo_account.id)
    assert result.months == []


# ---------------------------------------------------------------------------
# Growth YoY
# ---------------------------------------------------------------------------

def test_growth_yoy_multiple_years(db, demo_account):
    """Activities across 3 years are grouped correctly."""
    db.add_all([
        Activity(account_id=demo_account.id, alpaca_id="gy1",
                 activity_type="DIV", symbol="VTI",
                 net_amount=Decimal("100"), date=date(2024, 3, 15)),
        Activity(account_id=demo_account.id, alpaca_id="gy2",
                 activity_type="DIV", symbol="VTI",
                 net_amount=Decimal("120"), date=date(2025, 3, 15)),
        Activity(account_id=demo_account.id, alpaca_id="gy3",
                 activity_type="DIV", symbol="VTI",
                 net_amount=Decimal("150"), date=date(2026, 3, 15)),
    ])
    db.commit()

    result = get_growth_yoy(db, demo_account.id, years=3)
    assert len(result.years) == 3
    years_by_yr = {y.year: y for y in result.years}
    assert years_by_yr[2024].months[2].total == pytest.approx(100.0)  # March = index 2
    assert years_by_yr[2025].months[2].total == pytest.approx(120.0)
    assert years_by_yr[2026].months[2].total == pytest.approx(150.0)


# ---------------------------------------------------------------------------
# Future payments
# ---------------------------------------------------------------------------

def test_future_payments_returns_months(db, demo_account):
    """Future payments builds month list from forecast (needs positions + history)."""
    # Seed position + quarterly dividend history so forecast can project
    db.add(Position(
        account_id=demo_account.id, symbol="AAPL",
        qty=Decimal("10"), avg_entry_price=Decimal("150"),
        market_value=Decimal("1800"), unrealized_pl=Decimal("0"),
        unrealized_plpc=Decimal("0"), current_price=Decimal("180"),
    ))
    today = date.today()
    for i, months_ago in enumerate([1, 4, 7, 10]):
        db.add(Activity(
            account_id=demo_account.id, alpaca_id=f"fp{i}",
            activity_type="DIV", symbol="AAPL",
            net_amount=Decimal("6"),
            date=today - timedelta(days=months_ago * 30),
        ))
    db.commit()

    result = get_future_payments(db, demo_account.id, months=12)
    assert len(result.months) > 0
    # All months should have non-negative totals
    for m in result.months:
        assert m.total >= 0
        assert m.confirmed >= 0
        assert m.estimated >= 0
        assert m.total == pytest.approx(m.confirmed + m.estimated, abs=0.01)


# ---------------------------------------------------------------------------
# Curated dividend fallback
# ---------------------------------------------------------------------------

def test_curated_fallback_when_no_history(db, demo_account):
    """Positions in SPYI + QQQI with zero DIV activities → curated fallback rows."""
    db.add_all([
        Position(
            account_id=demo_account.id, symbol="SPYI",
            qty=Decimal("100"), avg_entry_price=Decimal("50"),
            market_value=Decimal("5200"), unrealized_pl=Decimal("0"),
            unrealized_plpc=Decimal("0"), current_price=Decimal("52"),
        ),
        Position(
            account_id=demo_account.id, symbol="QQQI",
            qty=Decimal("50"), avg_entry_price=Decimal("45"),
            market_value=Decimal("2400"), unrealized_pl=Decimal("0"),
            unrealized_plpc=Decimal("0"), current_price=Decimal("48"),
        ),
    ])
    db.commit()

    rows = get_dividends_by_symbol(db, demo_account.id)
    assert len(rows) == 2
    by_sym = {r.symbol: r for r in rows}

    spyi = by_sym["SPYI"]
    assert spyi.annual_dps == pytest.approx(5.40, abs=0.01)
    assert spyi.frequency == "monthly"
    assert spyi.total_received == 0.0
    assert spyi.ytd_received == 0.0
    assert spyi.current_qty == pytest.approx(100.0)
    assert spyi.projected_annual == pytest.approx(540.0, abs=0.01)

    qqqi = by_sym["QQQI"]
    assert qqqi.annual_dps == pytest.approx(8.40, abs=0.01)
    assert qqqi.frequency == "monthly"
    assert qqqi.total_received == 0.0
    assert qqqi.projected_annual == pytest.approx(420.0, abs=0.01)


def test_history_takes_precedence_over_curated(db, demo_account):
    """If historical DIV activities exist, curated values are NOT used."""
    today = date.today()
    db.add(Position(
        account_id=demo_account.id, symbol="SPYI",
        qty=Decimal("100"), avg_entry_price=Decimal("50"),
        market_value=Decimal("5200"), unrealized_pl=Decimal("0"),
        unrealized_plpc=Decimal("0"), current_price=Decimal("52"),
    ))
    # Add real dividend history — 3 monthly payments of $45 each
    for i in range(3):
        db.add(Activity(
            account_id=demo_account.id, alpaca_id=f"hist{i}",
            activity_type="DIV", symbol="SPYI",
            net_amount=Decimal("45.00"),
            date=today - timedelta(days=(i + 1) * 30),
        ))
    db.commit()

    rows = get_dividends_by_symbol(db, demo_account.id)
    assert len(rows) == 1
    row = rows[0]
    assert row.symbol == "SPYI"
    assert row.total_received == pytest.approx(135.0, abs=0.01)
    # annual_dps derived from history, not curated 5.40
    assert row.annual_dps == pytest.approx(1.35, abs=0.01)  # 135 / 100 shares


def test_calendar_populates_with_curated_only(db, demo_account):
    """End-to-end: calendar returns items for monthly ETFs via curated fallback."""
    db.add(Position(
        account_id=demo_account.id, symbol="SPYI",
        qty=Decimal("100"), avg_entry_price=Decimal("50"),
        market_value=Decimal("5200"), unrealized_pl=Decimal("0"),
        unrealized_plpc=Decimal("0"), current_price=Decimal("52"),
    ))
    db.commit()

    today = date.today()
    items = get_dividend_calendar(
        db, demo_account.id,
        from_date=str(today),
        to_date=str(today + timedelta(days=90)),
    )
    assert len(items) > 0
    # All items should be for SPYI with monthly cadence (~30-day spacing)
    for item in items:
        assert item.symbol == "SPYI"
        assert item.projected_income > 0
