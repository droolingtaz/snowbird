"""Tests for activities via REST and portfolio history backfill."""
from __future__ import annotations

from datetime import datetime, date, timezone, timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import select

from app.models.activity import Activity
from app.models.snapshot import PortfolioSnapshot
from app.services.sync import _sync_activities, _backfill_snapshots, sync_account


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


# ---------------------------------------------------------------------------
# Bug 1 — _sync_activities via raw REST
# ---------------------------------------------------------------------------

class TestSyncActivitiesREST:
    """Activities fetched via httpx GET to /v2/account/activities."""

    def test_dividends_written(self, db, demo_account):
        """DIV activities from REST response are persisted to the DB."""
        fake_resp = MagicMock()
        fake_resp.status_code = 200
        fake_resp.raise_for_status = MagicMock()
        fake_resp.json.return_value = [
            _fake_activity_json("act-001", "DIV", "AAPL", "1.50"),
            _fake_activity_json("act-002", "DIV", "MSFT", "2.75"),
            _fake_activity_json("act-003", "FILL", "TSLA", "0", qty="10", price="250.00"),
        ]

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
    """Portfolio history backfill writes daily snapshots."""

    def test_backfill_writes_snapshots(self, db, demo_account):
        """Backfill from 120-day history creates 120 snapshots."""
        mock_client = MagicMock()
        mock_client.get.return_value = _fake_portfolio_history(120)

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

    def test_backfill_idempotent(self, db, demo_account):
        """Running backfill twice does not double-insert."""
        mock_client = MagicMock()
        mock_client.get.return_value = _fake_portfolio_history(100)

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

        mock_client = MagicMock()
        mock_client.get.return_value = _fake_portfolio_history(5)

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

    def test_backfill_error_does_not_fail_sync(self, db, demo_account):
        """If client.get raises, backfill returns gracefully."""
        mock_client = MagicMock()
        mock_client.get.side_effect = Exception("API error")

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

        mock_client = MagicMock()
        mock_client.get.return_value = history

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
        mock_client.get.return_value = _fake_portfolio_history(30)

        fake_http_resp = MagicMock()
        fake_http_resp.status_code = 200
        fake_http_resp.raise_for_status = MagicMock()
        fake_http_resp.json.return_value = []

        with patch("app.services.sync.get_trading_client", return_value=mock_client), \
             patch("httpx.get", return_value=fake_http_resp):
            sync_account(db, demo_account)

        # Backfill should have inserted 30 + today's snapshot = 31 (or 30 if today overlaps)
        snapshots = db.execute(
            select(PortfolioSnapshot).where(
                PortfolioSnapshot.account_id == demo_account.id
            )
        ).scalars().all()
        assert len(snapshots) >= 30
        mock_client.get.assert_called_once()

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

        fake_http_resp = MagicMock()
        fake_http_resp.status_code = 200
        fake_http_resp.raise_for_status = MagicMock()
        fake_http_resp.json.return_value = []

        with patch("app.services.sync.get_trading_client", return_value=mock_client), \
             patch("httpx.get", return_value=fake_http_resp):
            sync_account(db, demo_account)

        # client.get should NOT have been called (no backfill)
        mock_client.get.assert_not_called()
