"""Modified Dietz monthly returns: contribution-adjusted return tests."""
from decimal import Decimal
from datetime import date, timedelta

import pytest

from app.models.snapshot import PortfolioSnapshot
from app.models.activity import Activity
from app.services.analytics import compute_monthly_returns


def _snap(db, account_id, d, equity):
    """Helper: insert a single snapshot."""
    s = PortfolioSnapshot(
        account_id=account_id, date=d,
        equity=Decimal(str(equity)), cash=Decimal("0"),
        long_market_value=Decimal(str(equity)), pnl=Decimal("0"),
    )
    db.add(s)
    return s


def _activity(db, account_id, activity_type, d, net_amount, idx=0, symbol=None):
    """Helper: insert a single activity."""
    a = Activity(
        account_id=account_id,
        alpaca_id=f"test-{activity_type}-{d}-{idx}",
        activity_type=activity_type,
        net_amount=Decimal(str(net_amount)),
        date=d,
        symbol=symbol,
        raw={},
    )
    db.add(a)
    return a


class TestModifiedDietzMonthlyReturns:

    def test_no_flows_matches_simple_return(self, db, demo_account):
        """With zero external flows, Modified Dietz equals (end-start)/start."""
        # Use a fixed month: 2025-03 (31 days)
        _snap(db, demo_account.id, date(2025, 3, 1), 10000)
        _snap(db, demo_account.id, date(2025, 3, 15), 10300)
        _snap(db, demo_account.id, date(2025, 3, 31), 10500)
        db.commit()

        results = compute_monthly_returns(db, demo_account.id)
        assert len(results) == 1

        r = results[0]
        assert r.year == 2025
        assert r.month == 3
        # Simple return: (10500 - 10000) / 10000 = 0.05
        assert r.return_pct is not None
        assert abs(r.return_pct - 0.05) < 1e-6

    def test_midmonth_deposit_does_not_inflate_return(self, db, demo_account):
        """$10k start, $5k deposit mid-month, $15k end → return ≈ 0%, not 50%."""
        # 2025-06 has 30 days
        _snap(db, demo_account.id, date(2025, 6, 1), 10000)
        _snap(db, demo_account.id, date(2025, 6, 30), 15000)
        # $5k deposit on day 15
        _activity(db, demo_account.id, "CSD", date(2025, 6, 15), 5000)
        db.commit()

        results = compute_monthly_returns(db, demo_account.id)
        assert len(results) == 1

        r = results[0]
        # Modified Dietz:
        # net_flows = 5000
        # weight = (30 - 14) / 30 = 16/30 ≈ 0.5333  (day_offset from June 1 = 14)
        # weighted_flows = 0.5333 * 5000 = 2666.67
        # denom = 10000 + 2666.67 = 12666.67
        # numerator = 15000 - 10000 - 5000 = 0
        # return = 0 / 12666.67 = 0.0
        assert r.return_pct is not None
        assert abs(r.return_pct) < 0.01  # ~0% return, not 50%

    def test_midmonth_withdrawal_does_not_deflate_return(self, db, demo_account):
        """$10k start, $5k withdrawal mid-month, $5k end → return ≈ 0%, not -50%."""
        # 2025-06 has 30 days
        _snap(db, demo_account.id, date(2025, 6, 1), 10000)
        _snap(db, demo_account.id, date(2025, 6, 30), 5000)
        # $5k withdrawal on day 15 (negative net_amount)
        _activity(db, demo_account.id, "CSW", date(2025, 6, 15), -5000)
        db.commit()

        results = compute_monthly_returns(db, demo_account.id)
        assert len(results) == 1

        r = results[0]
        # Modified Dietz:
        # net_flows = -5000
        # weight = (30 - 14) / 30 = 16/30
        # weighted_flows = 16/30 * (-5000) = -2666.67
        # denom = 10000 + (-2666.67) = 7333.33
        # numerator = 5000 - 10000 - (-5000) = 0
        # return = 0 / 7333.33 = 0.0
        assert r.return_pct is not None
        assert abs(r.return_pct) < 0.01  # ~0% return, not -50%

    def test_dividends_not_treated_as_external_flow(self, db, demo_account):
        """DIV activity should NOT be subtracted — it's internal equity growth."""
        # 2025-04 has 30 days
        _snap(db, demo_account.id, date(2025, 4, 1), 10000)
        _snap(db, demo_account.id, date(2025, 4, 30), 10200)
        # $200 dividend mid-month — this is NOT an external cash flow
        _activity(db, demo_account.id, "DIV", date(2025, 4, 15), 200, symbol="VTI")
        db.commit()

        results = compute_monthly_returns(db, demo_account.id)
        assert len(results) == 1

        r = results[0]
        # Without Modified Dietz adjustment for DIV:
        # return = (10200 - 10000) / 10000 = 0.02
        # The dividend drove the equity up and that IS real return.
        assert r.return_pct is not None
        assert abs(r.return_pct - 0.02) < 1e-6

    def test_buy_sell_not_treated_as_external_flow(self, db, demo_account):
        """FILL activities (buys/sells) are internal moves — not external flows."""
        # 2025-05 has 31 days
        _snap(db, demo_account.id, date(2025, 5, 1), 20000)
        _snap(db, demo_account.id, date(2025, 5, 31), 21000)
        # Buy 10 shares at $100 — FILL is internal, not external
        _activity(db, demo_account.id, "FILL", date(2025, 5, 15), -1000, symbol="AAPL")
        db.commit()

        results = compute_monthly_returns(db, demo_account.id)
        assert len(results) == 1

        r = results[0]
        # Simple return since no external flows: (21000 - 20000) / 20000 = 0.05
        assert r.return_pct is not None
        assert abs(r.return_pct - 0.05) < 1e-6

    def test_multiple_flows_in_one_month(self, db, demo_account):
        """Two deposits at different times, weighted independently."""
        # 2025-09 has 30 days
        _snap(db, demo_account.id, date(2025, 9, 1), 10000)
        _snap(db, demo_account.id, date(2025, 9, 30), 20500)

        # $5k deposit on day 10, $5k deposit on day 20
        _activity(db, demo_account.id, "CSD", date(2025, 9, 10), 5000, idx=0)
        _activity(db, demo_account.id, "CSD", date(2025, 9, 20), 5000, idx=1)
        db.commit()

        results = compute_monthly_returns(db, demo_account.id)
        assert len(results) == 1

        r = results[0]
        # Modified Dietz:
        # net_flows = 10000
        # Flow 1 (Sep 10): day_offset = 9,  weight = (30-9)/30  = 21/30 = 0.7
        # Flow 2 (Sep 20): day_offset = 19, weight = (30-19)/30 = 11/30 ≈ 0.3667
        # weighted_flows = 0.7 * 5000 + 0.3667 * 5000 = 3500 + 1833.33 = 5333.33
        # denom = 10000 + 5333.33 = 15333.33
        # numerator = 20500 - 10000 - 10000 = 500
        # return = 500 / 15333.33 ≈ 0.032609
        assert r.return_pct is not None
        assert abs(r.return_pct - 0.032609) < 0.001
