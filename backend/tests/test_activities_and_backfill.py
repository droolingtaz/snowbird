"""Tests for activities via REST and portfolio history backfill."""
from __future__ import annotations

from datetime import datetime, date, timezone, timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch, call

import pytest
from sqlalchemy import select

from app.models.activity import Activity
from app.models.snapshot import PortfolioSnapshot
from app.services.sync import (
    _sync_activities, _backfill_snapshots, sync_account,
    _MIN_LOOKBACK_DAYS, _MAX_LOOKBACK_DAYS,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fake_activity_json(activity_id, activity_type="DIV", symbol="AAPL",
                        net_amount="1.50", qty=None, price=None, dt=None):
    """Build a dict mimicking Alpaca GET /v2/account/activities JSON."""
    if dt is None:
        dt = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    d = {
        "id": activity_id,
        "activity_type": activity_type,
        "symbol": symbol,
        "net_amount": net_amount,
        "date": dt,
    }
    if qty is not None:
        d["qty"] = qty
    if price is not None:
        d["price"] = price
    return d


def _fake_portfolio_history(num_days=120):
    """Build a dict mimicking Alpaca GET /v2/account/portfolio/history JSON."""
    base_ts = int(datetime(2025, 1, 1, tzinfo=timezone.utc).timestamp())
    day_sec = 86400
    return {
        "timestamp": [base_ts + i * day_sec for i in range(num_days)],
        "equity": [10000.0 + i * 10.5 for i in range(num_days)],
        "profit_loss": [i * 10.5 for i in range(num_days)],
        "profit_loss_pct": [i * 0.001 for i in range(num_days)],
    }


def _mock_httpx_response(json_data, status_code=200):
    """Build a mock httpx.Response for use with patch('httpx.get')."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.raise_for_status = MagicMock()
    resp.json.return_value = json_data
    return resp


# ---------------------------------------------------------------------------
# Bug 1 — _sync_activities via raw REST
# ---------------------------------------------------------------------------

class TestSyncActivitiesREST:
    """Activities fetched via httpx GET to /v2/account/activities."""

    def test_dividends_written(self, db, demo_account):
        """DIV activities from REST response are persisted to the DB."""
        fake_resp = _mock_httpx_response([
            _fake_activity_json("act-001", "DIV", "AAPL", "1.50"),
            _fake_activity_json("act-002", "DIV", "MSFT", "2.75"),
            _fake_activity_json("act-003", "FILL", "TSLA", "0", qty="10", price="250.00"),
        ])

        mock_client = MagicMock()

        with patch("httpx.get", return_value=fake_resp) as mock_httpx_get:
            _sync_activities(db, mock_client, demo_account)

        activities = db.execute(
            select(Activity).where(Activity.account_id == demo_account.id)
        ).scalars().all()
        assert len(activities) == 3

        div_acts = [a for a in activities if a.activity_type == "DIV"]
        assert len(div_acts) == 2
        assert {a.symbol for a in div_acts} == {"AAPL", "MSFT"}
        assert div_acts[0].net_amount in (Decimal("1.50"), Decimal("2.75"))

    def test_no_activity_types_filter_sent(self, db, demo_account):
        """activity_types param must NOT be sent (Alpaca returns all types by default)."""
        fake_resp = _mock_httpx_response([])
        mock_client = MagicMock()

        with patch("httpx.get", return_value=fake_resp) as mock_httpx_get:
            _sync_activities(db, mock_client, demo_account)

        mock_httpx_get.assert_called_once()
        _, kwargs = mock_httpx_get.call_args
        assert "activity_types" not in kwargs.get("params", {})

    def test_duplicate_activities_skipped(self, db, demo_account):
        """Re-syncing the same activities does not create duplicates."""
        fake_resp = MagicMock()
        fake_resp.status_code = 200
        fake_resp.raise_for_status = MagicMock()
        fake_resp.json.return_value = [
            _fake_activity_json("act-001", "DIV", "AAPL", "1.50"),
        ]

        mock_client = MagicMock()

        with patch("httpx.get", return_value=fake_resp) as mock_httpx_get:
            _sync_activities(db, mock_client, demo_account)
            db.flush()
            _sync_activities(db, mock_client, demo_account)
            db.flush()

        activities = db.execute(
            select(Activity).where(Activity.account_id == demo_account.id)
        ).scalars().all()
        assert len(activities) == 1

    def test_activities_error_does_not_abort_sync(self, db, demo_account):
        """If httpx.get raises, _sync_activities returns gracefully."""
        mock_client = MagicMock()

        with patch("httpx.get", side_effect=Exception("connection refused")):
            # Should not raise
            _sync_activities(db, mock_client, demo_account)

        activities = db.execute(
            select(Activity).where(Activity.account_id == demo_account.id)
        ).scalars().all()
        assert len(activities) == 0

    def test_activities_with_transaction_time(self, db, demo_account):
        """Activities that use transaction_time instead of date are handled."""
        fake_resp = MagicMock()
        fake_resp.status_code = 200
        fake_resp.raise_for_status = MagicMock()
        fake_resp.json.return_value = [{
            "id": "act-tx-001",
            "activity_type": "FILL",
            "symbol": "GOOG",
            "qty": "5",
            "price": "175.00",
            "net_amount": "0",
            "transaction_time": "2025-06-15T14:30:00Z",
        }]

        mock_client = MagicMock()

        with patch("httpx.get", return_value=fake_resp) as mock_httpx_get:
            _sync_activities(db, mock_client, demo_account)

        act = db.execute(
            select(Activity).where(Activity.alpaca_id == "act-tx-001")
        ).scalar_one()
        assert act.date == date(2025, 6, 15)
        assert act.symbol == "GOOG"

    def test_activities_empty_id_skipped(self, db, demo_account):
        """Activities with no id field are skipped."""
        fake_resp = MagicMock()
        fake_resp.status_code = 200
        fake_resp.raise_for_status = MagicMock()
        fake_resp.json.return_value = [
            {"activity_type": "DIV", "symbol": "X", "net_amount": "1"},  # no id
            _fake_activity_json("act-valid", "DIV", "Y", "2"),
        ]

        mock_client = MagicMock()

        with patch("httpx.get", return_value=fake_resp) as mock_httpx_get:
            _sync_activities(db, mock_client, demo_account)

        activities = db.execute(
            select(Activity).where(Activity.account_id == demo_account.id)
        ).scalars().all()
        assert len(activities) == 1
        assert activities[0].alpaca_id == "act-valid"


# ---------------------------------------------------------------------------
# Bug 2 — _backfill_snapshots via portfolio history
# ---------------------------------------------------------------------------

class TestBackfillSnapshots:
    """Portfolio history backfill via httpx.get writes daily snapshots."""

    def test_backfill_writes_snapshots(self, db, demo_account):
        """Backfill from 120-day history creates 120 snapshots."""
        fake_resp = _mock_httpx_response(_fake_portfolio_history(120))
        mock_client = MagicMock()

        with patch("httpx.get", return_value=fake_resp):
            _backfill_snapshots(db, mock_client, demo_account)

        snapshots = db.execute(
            select(PortfolioSnapshot).where(
                PortfolioSnapshot.account_id == demo_account.id
            )
        ).scalars().all()
        assert len(snapshots) == 120

        # Verify data integrity of first snapshot
        first = sorted(snapshots, key=lambda s: s.date)[0]
        assert first.date == date(2025, 1, 1)
        assert first.equity == Decimal("10000.0")

    def test_backfill_calls_correct_url(self, db, demo_account):
        """httpx.get is called with the account's base_url + /v2/account/portfolio/history."""
        fake_resp = _mock_httpx_response(_fake_portfolio_history(10))
        mock_client = MagicMock()

        with patch("httpx.get", return_value=fake_resp) as mock_httpx_get:
            _backfill_snapshots(db, mock_client, demo_account)

        mock_httpx_get.assert_called_once()
        args, kwargs = mock_httpx_get.call_args
        assert args[0] == "https://paper-api.alpaca.markets/v2/account/portfolio/history"
        assert kwargs["params"] == {"period": "1A", "timeframe": "1D"}
        assert "APCA-API-KEY-ID" in kwargs["headers"]

    def test_backfill_realistic_10day_history(self, db, demo_account):
        """Realistic 10-day Alpaca portfolio history JSON produces correct snapshots."""
        history = _fake_portfolio_history(10)
        fake_resp = _mock_httpx_response(history)
        mock_client = MagicMock()

        with patch("httpx.get", return_value=fake_resp):
            _backfill_snapshots(db, mock_client, demo_account)

        snapshots = db.execute(
            select(PortfolioSnapshot).where(
                PortfolioSnapshot.account_id == demo_account.id
            ).order_by(PortfolioSnapshot.date)
        ).scalars().all()
        assert len(snapshots) == 10

        # Verify first and last
        assert snapshots[0].date == date(2025, 1, 1)
        assert snapshots[0].equity == Decimal("10000.0")
        assert snapshots[0].pnl == Decimal("0.0")
        assert snapshots[9].date == date(2025, 1, 10)
        assert snapshots[9].equity == Decimal(str(10000.0 + 9 * 10.5))
        assert snapshots[9].pnl == Decimal(str(9 * 10.5))

    def test_backfill_idempotent(self, db, demo_account):
        """Running backfill twice does not double-insert."""
        fake_resp = _mock_httpx_response(_fake_portfolio_history(100))
        mock_client = MagicMock()

        with patch("httpx.get", return_value=fake_resp):
            _backfill_snapshots(db, mock_client, demo_account)
            db.flush()
            _backfill_snapshots(db, mock_client, demo_account)
            db.flush()

        count = db.execute(
            select(PortfolioSnapshot).where(
                PortfolioSnapshot.account_id == demo_account.id
            )
        ).scalars().all()
        assert len(count) == 100

    def test_backfill_does_not_overwrite_existing(self, db, demo_account):
        """If _snapshot_equity already wrote today's snapshot, backfill skips it."""
        today = date(2025, 1, 1)
        existing_snap = PortfolioSnapshot(
            account_id=demo_account.id,
            date=today,
            equity=Decimal("99999.99"),
            cash=Decimal("5000"),
        )
        db.add(existing_snap)
        db.flush()

        fake_resp = _mock_httpx_response(_fake_portfolio_history(5))
        mock_client = MagicMock()

        with patch("httpx.get", return_value=fake_resp):
            _backfill_snapshots(db, mock_client, demo_account)

        snap = db.execute(
            select(PortfolioSnapshot).where(
                PortfolioSnapshot.account_id == demo_account.id,
                PortfolioSnapshot.date == today,
            )
        ).scalar_one()
        # Should keep the original value, not overwrite
        assert snap.equity == Decimal("99999.99")
        assert snap.cash == Decimal("5000")

    def test_backfill_with_preexisting_today_snapshot(self, db, demo_account):
        """Regression: snapshot for a date in the backfill payload already exists.

        Reproduces the production bug where _snapshot_equity (or fast_sync)
        writes today's row before _backfill_snapshots runs. The backfill
        payload includes that same date. With ON CONFLICT DO NOTHING the
        insert must silently skip the conflicting row — no UniqueViolation.
        """
        # Pre-insert a snapshot for 2025-01-03 (day index 2 in the history)
        conflict_date = date(2025, 1, 3)
        existing_snap = PortfolioSnapshot(
            account_id=demo_account.id,
            date=conflict_date,
            equity=Decimal("55555.55"),
            cash=Decimal("1111.11"),
        )
        db.add(existing_snap)
        db.flush()

        # Backfill 5 days (2025-01-01 through 2025-01-05) — includes 2025-01-03
        fake_resp = _mock_httpx_response(_fake_portfolio_history(5))
        mock_client = MagicMock()

        with patch("httpx.get", return_value=fake_resp):
            # Must not raise UniqueViolation
            _backfill_snapshots(db, mock_client, demo_account)

        all_snaps = db.execute(
            select(PortfolioSnapshot).where(
                PortfolioSnapshot.account_id == demo_account.id
            )
        ).scalars().all()
        # 4 new + 1 pre-existing = 5 total
        assert len(all_snaps) == 5

        # The conflicting row must retain its original values (DO NOTHING)
        conflict_snap = db.execute(
            select(PortfolioSnapshot).where(
                PortfolioSnapshot.account_id == demo_account.id,
                PortfolioSnapshot.date == conflict_date,
            )
        ).scalar_one()
        assert conflict_snap.equity == Decimal("55555.55")
        assert conflict_snap.cash == Decimal("1111.11")

    def test_backfill_error_does_not_fail_sync(self, db, demo_account):
        """If httpx.get raises, backfill returns gracefully."""
        mock_client = MagicMock()

        with patch("httpx.get", side_effect=Exception("API error")):
            # Should not raise
            _backfill_snapshots(db, mock_client, demo_account)

        snapshots = db.execute(
            select(PortfolioSnapshot).where(
                PortfolioSnapshot.account_id == demo_account.id
            )
        ).scalars().all()
        assert len(snapshots) == 0

    def test_backfill_skips_null_equity(self, db, demo_account):
        """Days with null equity in history are skipped."""
        history = _fake_portfolio_history(5)
        history["equity"][2] = None  # null out day 3

        fake_resp = _mock_httpx_response(history)
        mock_client = MagicMock()

        with patch("httpx.get", return_value=fake_resp):
            _backfill_snapshots(db, mock_client, demo_account)

        snapshots = db.execute(
            select(PortfolioSnapshot).where(
                PortfolioSnapshot.account_id == demo_account.id
            )
        ).scalars().all()
        assert len(snapshots) == 4  # 5 minus 1 null


# ---------------------------------------------------------------------------
# Integration: sync_account calls backfill on first sync only
# ---------------------------------------------------------------------------

class TestSyncAccountBackfillIntegration:
    """sync_account calls _backfill_snapshots only when last_sync_at is None."""

    def test_first_sync_triggers_backfill(self, db, demo_account):
        """Backfill runs on first sync (last_sync_at=None)."""
        assert demo_account.last_sync_at is None

        mock_client = MagicMock()
        mock_client.get_all_positions.return_value = []
        mock_client.get_orders.return_value = []
        mock_client.get_account.return_value = MagicMock(
            equity="10000", cash="2000", long_market_value="8000",
        )

        # httpx.get is called for both backfill (portfolio history) and activities
        call_count = [0]
        def _fake_httpx_get(url, **kwargs):
            call_count[0] += 1
            if "portfolio/history" in url:
                return _mock_httpx_response(_fake_portfolio_history(30))
            return _mock_httpx_response([])  # activities

        with patch("app.services.sync.get_trading_client", return_value=mock_client), \
             patch("httpx.get", side_effect=_fake_httpx_get):
            sync_account(db, demo_account)

        # Backfill should have inserted 30 + today's snapshot = 31 (or 30 if today overlaps)
        snapshots = db.execute(
            select(PortfolioSnapshot).where(
                PortfolioSnapshot.account_id == demo_account.id
            )
        ).scalars().all()
        assert len(snapshots) >= 30
        assert call_count[0] == 2  # one for backfill, one for activities

    def test_full_sync_twice_is_idempotent(self, db, demo_account):
        """Running sync_account twice (first sync with backfill) does not raise."""
        assert demo_account.last_sync_at is None

        mock_client = MagicMock()
        mock_client.get_all_positions.return_value = []
        mock_client.get_orders.return_value = []
        mock_client.get_account.return_value = MagicMock(
            equity="10000", cash="2000", long_market_value="8000",
        )

        def _fake_httpx_get(url, **kwargs):
            if "portfolio/history" in url:
                return _mock_httpx_response(_fake_portfolio_history(30))
            return _mock_httpx_response([])  # activities

        with patch("app.services.sync.get_trading_client", return_value=mock_client), \
             patch("httpx.get", side_effect=_fake_httpx_get):
            sync_account(db, demo_account)

        # Reset last_sync_at to simulate a retry that triggers backfill again
        demo_account.last_sync_at = None
        db.flush()

        with patch("app.services.sync.get_trading_client", return_value=mock_client), \
             patch("httpx.get", side_effect=_fake_httpx_get):
            # Second sync must not raise (idempotent backfill)
            sync_account(db, demo_account)

        snapshots = db.execute(
            select(PortfolioSnapshot).where(
                PortfolioSnapshot.account_id == demo_account.id
            )
        ).scalars().all()
        # Should still have ~31 snapshots (30 backfill + 1 today), not doubled
        assert 30 <= len(snapshots) <= 32

    def test_sync_error_does_not_raise_pending_rollback(self, db, demo_account):
        """A DB error in sync_account is handled gracefully without PendingRollbackError."""
        mock_client = MagicMock()
        mock_client.get_all_positions.side_effect = RuntimeError("simulated DB failure")

        with patch("app.services.sync.get_trading_client", return_value=mock_client):
            # Must not raise — the except handler should rollback and log
            sync_account(db, demo_account)

        # Session should still be usable after the error
        snapshots = db.execute(
            select(PortfolioSnapshot).where(
                PortfolioSnapshot.account_id == demo_account.id
            )
        ).scalars().all()
        assert len(snapshots) == 0

    def test_subsequent_sync_skips_backfill(self, db, demo_account):
        """Backfill is NOT called when last_sync_at is set."""
        demo_account.last_sync_at = datetime.now(timezone.utc)
        db.flush()

        mock_client = MagicMock()
        mock_client.get_all_positions.return_value = []
        mock_client.get_orders.return_value = []
        mock_client.get_account.return_value = MagicMock(
            equity="10000", cash="2000", long_market_value="8000",
        )

        def _fake_httpx_get(url, **kwargs):
            # Only activities call should happen, no portfolio/history
            assert "portfolio/history" not in url
            return _mock_httpx_response([])

        with patch("app.services.sync.get_trading_client", return_value=mock_client), \
             patch("httpx.get", side_effect=_fake_httpx_get) as mock_httpx_get:
            sync_account(db, demo_account)

        # httpx.get called once for activities only (no backfill)
        assert mock_httpx_get.call_count == 1


# ---------------------------------------------------------------------------
# Dynamic activity lookback
# ---------------------------------------------------------------------------

class TestDynamicActivityLookback:
    """_sync_activities computes lookback from the most recent stored activity."""

    def _extract_after_param(self, mock_httpx_get) -> str:
        """Pull the 'after' query param from the httpx.get call."""
        _, kwargs = mock_httpx_get.call_args
        return kwargs["params"]["after"]

    def test_first_sync_uses_max_lookback(self, db, demo_account):
        """No activities in the DB → lookback = _MAX_LOOKBACK_DAYS (90)."""
        fake_resp = _mock_httpx_response([])
        mock_client = MagicMock()

        with patch("httpx.get", return_value=fake_resp) as mock_httpx_get:
            _sync_activities(db, mock_client, demo_account)

        after_str = self._extract_after_param(mock_httpx_get)
        after_dt = datetime.strptime(after_str, "%Y-%m-%dT%H:%M:%SZ")
        expected = datetime.now(timezone.utc) - timedelta(days=_MAX_LOOKBACK_DAYS)
        # Allow 60 seconds of clock drift
        assert abs((after_dt - expected.replace(tzinfo=None)).total_seconds()) < 60

    def test_recent_activity_uses_min_lookback(self, db, demo_account):
        """Most recent activity is 5 days ago → gap+2=7 → clamped to MIN (7)."""
        recent_date = date.today() - timedelta(days=5)
        act = Activity(
            account_id=demo_account.id,
            alpaca_id="recent-001",
            activity_type="DIV",
            symbol="AAPL",
            net_amount=Decimal("1.00"),
            date=recent_date,
            raw={},
        )
        db.add(act)
        db.flush()

        fake_resp = _mock_httpx_response([])
        mock_client = MagicMock()

        with patch("httpx.get", return_value=fake_resp) as mock_httpx_get:
            _sync_activities(db, mock_client, demo_account)

        after_str = self._extract_after_param(mock_httpx_get)
        after_dt = datetime.strptime(after_str, "%Y-%m-%dT%H:%M:%SZ")
        expected = datetime.now(timezone.utc) - timedelta(days=_MIN_LOOKBACK_DAYS)
        assert abs((after_dt - expected.replace(tzinfo=None)).total_seconds()) < 60

    def test_30day_gap_uses_gap_plus_margin(self, db, demo_account):
        """Most recent activity is 30 days ago → gap+2=32 days lookback."""
        old_date = date.today() - timedelta(days=30)
        act = Activity(
            account_id=demo_account.id,
            alpaca_id="gap-001",
            activity_type="FILL",
            symbol="TSLA",
            net_amount=Decimal("0"),
            date=old_date,
            raw={},
        )
        db.add(act)
        db.flush()

        fake_resp = _mock_httpx_response([])
        mock_client = MagicMock()

        with patch("httpx.get", return_value=fake_resp) as mock_httpx_get:
            _sync_activities(db, mock_client, demo_account)

        after_str = self._extract_after_param(mock_httpx_get)
        after_dt = datetime.strptime(after_str, "%Y-%m-%dT%H:%M:%SZ")
        expected = datetime.now(timezone.utc) - timedelta(days=32)
        assert abs((after_dt - expected.replace(tzinfo=None)).total_seconds()) < 60

    def test_200day_gap_capped_at_max(self, db, demo_account):
        """Most recent activity is 200 days ago → gap+2=202 → clamped to MAX (90)."""
        ancient_date = date.today() - timedelta(days=200)
        act = Activity(
            account_id=demo_account.id,
            alpaca_id="ancient-001",
            activity_type="DIV",
            symbol="VTI",
            net_amount=Decimal("5.00"),
            date=ancient_date,
            raw={},
        )
        db.add(act)
        db.flush()

        fake_resp = _mock_httpx_response([])
        mock_client = MagicMock()

        with patch("httpx.get", return_value=fake_resp) as mock_httpx_get:
            _sync_activities(db, mock_client, demo_account)

        after_str = self._extract_after_param(mock_httpx_get)
        after_dt = datetime.strptime(after_str, "%Y-%m-%dT%H:%M:%SZ")
        expected = datetime.now(timezone.utc) - timedelta(days=_MAX_LOOKBACK_DAYS)
        assert abs((after_dt - expected.replace(tzinfo=None)).total_seconds()) < 60
