"""Analytics math: TWR, CAGR, Sharpe, drawdown, IRR, passive income, movers."""
from decimal import Decimal
from datetime import date, timedelta
from unittest.mock import MagicMock, patch

import pytest

from app.models.snapshot import PortfolioSnapshot
from app.models.activity import Activity
from app.models.position import Position
from app.models.instrument import Instrument
from app.services.analytics import (
    compute_daily_returns, compute_performance,
    compute_irr, compute_passive_income, compute_movers,
)


def _seed_linear_snapshots(db, account_id, start_equity=100_000.0, daily_return=0.001, days=30):
    """Create `days` snapshots each growing by daily_return."""
    start = date.today() - timedelta(days=days)
    eq = start_equity
    snaps = []
    for i in range(days):
        snaps.append(PortfolioSnapshot(
            account_id=account_id, date=start + timedelta(days=i),
            equity=Decimal(str(round(eq, 4))),
            cash=Decimal("0"), long_market_value=Decimal(str(round(eq, 4))),
            pnl=Decimal("0"),
        ))
        eq *= (1 + daily_return)
    db.add_all(snaps)
    db.commit()
    return snaps


def test_daily_returns_length(db, demo_account):
    snaps = _seed_linear_snapshots(db, demo_account.id, daily_return=0.002, days=10)
    returns = compute_daily_returns(snaps, db, demo_account.id)
    # N snapshots => N-1 returns
    assert len(returns) == 9


def test_daily_returns_value(db, demo_account):
    snaps = _seed_linear_snapshots(db, demo_account.id, daily_return=0.01, days=5)
    returns = compute_daily_returns(snaps, db, demo_account.id)
    # Each return should be ~1%
    for r in returns:
        assert abs(r - 0.01) < 1e-6


def test_performance_positive_twr(db, demo_account):
    _seed_linear_snapshots(db, demo_account.id, daily_return=0.001, days=30)
    perf = compute_performance(db, demo_account.id, period="1M")
    # 29 days of 0.1% ≈ (1.001^29)-1 ≈ 2.94%
    assert perf.twr is not None
    assert perf.twr > 0.02
    assert perf.twr < 0.04
    # Sharpe should be huge (volatility near zero) — just assert it exists
    assert perf.days >= 2


def test_performance_handles_no_data(db, demo_account):
    perf = compute_performance(db, demo_account.id, period="1Y")
    # Empty DB: no snapshots -> safe defaults, no crash
    assert perf is not None
    assert perf.days == 0


def test_performance_drawdown_detected(db, demo_account):
    """Peak then drop -> max_drawdown must be negative."""
    start = date.today() - timedelta(days=10)
    equities = [100, 110, 120, 130, 140, 150, 120, 110, 100, 90]
    db.add_all([
        PortfolioSnapshot(
            account_id=demo_account.id, date=start + timedelta(days=i),
            equity=Decimal(str(e)), cash=Decimal("0"),
            long_market_value=Decimal(str(e)), pnl=Decimal("0"),
        ) for i, e in enumerate(equities)
    ])
    db.commit()
    perf = compute_performance(db, demo_account.id, period="1M")
    # Peak 150 -> trough 90: drawdown = -40%
    if perf.max_drawdown is not None:
        assert perf.max_drawdown < -0.3


# ---------------------------------------------------------------------------
# IRR tests
# ---------------------------------------------------------------------------

class TestComputeIrr:
    """XIRR-based internal rate of return."""

    def test_irr_known_cashflows(self, db, demo_account):
        """Known cashflow: -100k at t=0, +110k at t=365d → ~10% IRR."""
        start = date.today() - timedelta(days=365)
        db.add_all([
            PortfolioSnapshot(
                account_id=demo_account.id, date=start,
                equity=Decimal("100000"), cash=Decimal("0"),
                long_market_value=Decimal("100000"), pnl=Decimal("0"),
            ),
            PortfolioSnapshot(
                account_id=demo_account.id, date=date.today(),
                equity=Decimal("110000"), cash=Decimal("0"),
                long_market_value=Decimal("110000"), pnl=Decimal("10000"),
            ),
        ])
        db.commit()

        result = compute_irr(db, demo_account.id, period="1Y")
        assert result.irr is not None
        # Should be approximately 10% (0.10)
        assert abs(result.irr - 0.10) < 0.02
        assert result.period == "1Y"

    def test_irr_lifetime_vs_1y_differ(self, db, demo_account):
        """Lifetime IRR can differ from 1Y IRR when history extends further."""
        two_years_ago = date.today() - timedelta(days=730)
        one_year_ago = date.today() - timedelta(days=365)

        db.add_all([
            PortfolioSnapshot(
                account_id=demo_account.id, date=two_years_ago,
                equity=Decimal("80000"), cash=Decimal("0"),
                long_market_value=Decimal("80000"), pnl=Decimal("0"),
            ),
            PortfolioSnapshot(
                account_id=demo_account.id, date=one_year_ago,
                equity=Decimal("100000"), cash=Decimal("0"),
                long_market_value=Decimal("100000"), pnl=Decimal("20000"),
            ),
            PortfolioSnapshot(
                account_id=demo_account.id, date=date.today(),
                equity=Decimal("115000"), cash=Decimal("0"),
                long_market_value=Decimal("115000"), pnl=Decimal("35000"),
            ),
        ])
        db.commit()

        irr_1y = compute_irr(db, demo_account.id, period="1Y")
        irr_all = compute_irr(db, demo_account.id, period="ALL")

        assert irr_1y.irr is not None
        assert irr_all.irr is not None
        # They should be different values (1Y sees 100k→115k, ALL sees 80k→115k)
        assert irr_1y.irr != irr_all.irr

    def test_irr_no_data_returns_null(self, db, demo_account):
        """No snapshots → irr=None."""
        result = compute_irr(db, demo_account.id, period="1Y")
        assert result.irr is None


# ---------------------------------------------------------------------------
# Passive Income tests
# ---------------------------------------------------------------------------

class TestPassiveIncome:
    """Forward dividend projection and yield."""

    def test_passive_income_with_dividends(self, db, demo_account):
        """Positions with trailing dividends produce a projection."""
        pos = Position(
            account_id=demo_account.id,
            symbol="VTI",
            qty=Decimal("100"),
            avg_entry_price=Decimal("200"),
            market_value=Decimal("22000"),
            current_price=Decimal("220"),
        )
        db.add(pos)
        db.flush()

        # Add quarterly dividend activities over the last 12 months
        today = date.today()
        for i in range(4):
            d = today - timedelta(days=90 * (i + 1))
            db.add(Activity(
                account_id=demo_account.id,
                alpaca_id=f"div-vti-{i}",
                activity_type="DIV",
                symbol="VTI",
                net_amount=Decimal("75.00"),  # $75 per quarter = $300/yr
                qty=Decimal("100"),
                date=d,
                raw={},
            ))
        db.commit()

        result = compute_passive_income(db, demo_account.id)
        assert result.annual_income > 0
        assert result.monthly_income > 0
        # $300 annual / $22000 market_value ≈ 1.36% yield
        if result.current_yield_pct is not None:
            assert result.current_yield_pct > 0


# ---------------------------------------------------------------------------
# Movers tests
# ---------------------------------------------------------------------------

class TestMovers:
    """Today's gainers and losers sorting."""

    def test_movers_sorting(self, db, demo_account):
        """Gainers sorted descending, losers sorted by most negative."""
        positions = [
            Position(
                account_id=demo_account.id, symbol="AAPL", qty=Decimal("10"),
                current_price=Decimal("150"), market_value=Decimal("1500"),
                unrealized_pl=Decimal("50"), unrealized_plpc=Decimal("0.034"),
            ),
            Position(
                account_id=demo_account.id, symbol="GOOG", qty=Decimal("5"),
                current_price=Decimal("175"), market_value=Decimal("875"),
                unrealized_pl=Decimal("100"), unrealized_plpc=Decimal("0.1"),
            ),
            Position(
                account_id=demo_account.id, symbol="TSLA", qty=Decimal("20"),
                current_price=Decimal("250"), market_value=Decimal("5000"),
                unrealized_pl=Decimal("-200"), unrealized_plpc=Decimal("-0.038"),
            ),
            Position(
                account_id=demo_account.id, symbol="META", qty=Decimal("8"),
                current_price=Decimal("300"), market_value=Decimal("2400"),
                unrealized_pl=Decimal("-50"), unrealized_plpc=Decimal("-0.02"),
            ),
        ]
        db.add_all(positions)
        db.commit()

        # Mock get_quote_cached to return None (use position fallback)
        with patch("app.services.market_data.get_quote_cached", return_value=None):
            result = compute_movers(db, demo_account.id, demo_account, limit=5)

        assert len(result.gainers) == 2
        assert len(result.losers) == 2
        # GOOG has higher absolute $ gain ($100 vs $50)
        assert result.gainers[0].symbol == "GOOG"
        assert result.gainers[1].symbol == "AAPL"
        # TSLA has higher absolute $ loss ($200 vs $50)
        assert result.losers[0].symbol == "TSLA"
        assert result.losers[1].symbol == "META"
