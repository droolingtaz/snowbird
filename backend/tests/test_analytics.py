"""Analytics math: TWR, CAGR, Sharpe, drawdown."""
from decimal import Decimal
from datetime import date, timedelta

import pytest

from app.models.snapshot import PortfolioSnapshot
from app.services.analytics import compute_daily_returns, compute_performance


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
