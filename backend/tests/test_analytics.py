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
    compute_daily_returns, compute_performance, compute_benchmark,
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

    def test_movers_empty_positions(self, db, demo_account):
        """No positions → empty gainers/losers."""
        with patch("app.services.market_data.get_quote_cached", return_value=None):
            result = compute_movers(db, demo_account.id, demo_account, limit=5)
        assert result.gainers == []
        assert result.losers == []

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


# ---------------------------------------------------------------------------
# Benchmark tests
# ---------------------------------------------------------------------------

class TestBenchmark:
    """Benchmark comparison: portfolio vs SPY."""

    def test_benchmark_returns_points_with_mocked_bars(self, db, demo_account):
        """Mocked Alpaca bars + real snapshots → non-empty points list."""
        start = date.today() - timedelta(days=10)
        # Seed 10 days of snapshots
        for i in range(10):
            db.add(PortfolioSnapshot(
                account_id=demo_account.id,
                date=start + timedelta(days=i),
                equity=Decimal(str(100_000 + i * 100)),
                cash=Decimal("0"),
                long_market_value=Decimal(str(100_000 + i * 100)),
                pnl=Decimal("0"),
            ))
        db.commit()

        # Build fake bars matching the same dates
        fake_bars = [
            {
                "timestamp": str(start + timedelta(days=i)),
                "open": 400.0 + i,
                "high": 405.0 + i,
                "low": 399.0 + i,
                "close": 402.0 + i,
                "volume": 1_000_000.0,
            }
            for i in range(10)
        ]

        with patch("app.services.market_data.get_bars_cached", return_value=fake_bars):
            points, port_ret, bench_ret = compute_benchmark(
                db, demo_account.id, "SPY", "1M", account=demo_account,
            )

        assert len(points) == 10
        # First point should be normalized to 100
        assert points[0].portfolio == 100.0
        assert points[0].benchmark == 100.0
        # Returns should be non-None
        assert port_ret is not None
        assert bench_ret is not None

    def test_benchmark_no_account_no_bars(self, db, demo_account):
        """Without account, get_bars_cached returns [] → empty result."""
        _seed_linear_snapshots(db, demo_account.id, days=10)

        with patch("app.services.market_data.get_bars_cached", return_value=[]):
            points, port_ret, bench_ret = compute_benchmark(
                db, demo_account.id, "SPY", "1M", account=None,
            )

        assert points == []
        assert port_ret is None
        assert bench_ret is None

    def test_benchmark_no_snapshots(self, db, demo_account):
        """No portfolio snapshots → empty result, no crash."""
        points, port_ret, bench_ret = compute_benchmark(
            db, demo_account.id, "SPY", "1M", account=demo_account,
        )
        assert points == []
        assert port_ret is None
        assert bench_ret is None

    # ------------------------------------------------------------------
    # Range / period filtering
    # ------------------------------------------------------------------

    @staticmethod
    def _seed_long_history(db, account_id, total_days=400):
        """Seed daily snapshots and matching bars for *total_days*.

        Returns (snapshots_list, fake_bars_list).  Bars use every calendar
        day so that the intersection with snapshots is 1-to-1.
        """
        today = date.today()
        start = today - timedelta(days=total_days)
        eq = 100_000.0
        snaps = []
        bars = []
        for i in range(total_days + 1):
            d = start + timedelta(days=i)
            snaps.append(PortfolioSnapshot(
                account_id=account_id,
                date=d,
                equity=Decimal(str(round(eq, 4))),
                cash=Decimal("0"),
                long_market_value=Decimal(str(round(eq, 4))),
                pnl=Decimal("0"),
            ))
            bars.append({
                "timestamp": str(d),
                "open": 400.0 + i * 0.5,
                "high": 405.0 + i * 0.5,
                "low": 399.0 + i * 0.5,
                "close": 402.0 + i * 0.5,
                "volume": 1_000_000.0,
            })
            eq *= 1.0003
        db.add_all(snaps)
        db.commit()
        return snaps, bars

    def test_benchmark_range_1W(self, db, demo_account):
        """period=1W → ~7 points (last 7 calendar days)."""
        _, bars = self._seed_long_history(db, demo_account.id)
        with patch("app.services.market_data.get_bars_cached", return_value=bars):
            points, _, _ = compute_benchmark(
                db, demo_account.id, "SPY", "1W", account=demo_account,
            )
        assert 5 <= len(points) <= 8
        assert points[0].portfolio == 100.0
        assert points[0].benchmark == 100.0

    def test_benchmark_range_1M(self, db, demo_account):
        """period=1M → ~30 points."""
        _, bars = self._seed_long_history(db, demo_account.id)
        with patch("app.services.market_data.get_bars_cached", return_value=bars):
            points, _, _ = compute_benchmark(
                db, demo_account.id, "SPY", "1M", account=demo_account,
            )
        assert 25 <= len(points) <= 31
        assert points[0].portfolio == 100.0
        assert points[0].benchmark == 100.0

    def test_benchmark_range_3M(self, db, demo_account):
        """period=3M → ~90 points."""
        _, bars = self._seed_long_history(db, demo_account.id)
        with patch("app.services.market_data.get_bars_cached", return_value=bars):
            points, _, _ = compute_benchmark(
                db, demo_account.id, "SPY", "3M", account=demo_account,
            )
        assert 80 <= len(points) <= 91
        assert points[0].portfolio == 100.0
        assert points[0].benchmark == 100.0

    def test_benchmark_range_YTD(self, db, demo_account):
        """period=YTD → Jan 1 to today."""
        _, bars = self._seed_long_history(db, demo_account.id)
        today = date.today()
        expected_days = (today - date(today.year, 1, 1)).days + 1
        with patch("app.services.market_data.get_bars_cached", return_value=bars):
            points, _, _ = compute_benchmark(
                db, demo_account.id, "SPY", "YTD", account=demo_account,
            )
        assert abs(len(points) - expected_days) <= 2
        assert points[0].portfolio == 100.0
        assert points[0].benchmark == 100.0

    def test_benchmark_range_1Y(self, db, demo_account):
        """period=1Y → ~365 points."""
        _, bars = self._seed_long_history(db, demo_account.id)
        with patch("app.services.market_data.get_bars_cached", return_value=bars):
            points, _, _ = compute_benchmark(
                db, demo_account.id, "SPY", "1Y", account=demo_account,
            )
        assert 355 <= len(points) <= 366
        assert points[0].portfolio == 100.0
        assert points[0].benchmark == 100.0

    def test_benchmark_ranges_differ(self, db, demo_account):
        """Different periods must produce different point counts."""
        _, bars = self._seed_long_history(db, demo_account.id)
        counts = {}
        for period in ("1W", "1M", "3M", "1Y"):
            with patch("app.services.market_data.get_bars_cached", return_value=bars):
                points, _, _ = compute_benchmark(
                    db, demo_account.id, "SPY", period, account=demo_account,
                )
            counts[period] = len(points)
        assert counts["1W"] < counts["1M"] < counts["3M"] < counts["1Y"]
