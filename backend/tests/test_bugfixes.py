"""Tests for the three bug fixes: sync isolation, multi-account market, delete auth."""
from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.main import app
from app.models import user, account, instrument, position, order, activity, bucket, snapshot  # noqa: F401
from app.models.user import User
from app.models.account import AlpacaAccount
from app.models.position import Position
from app.security import hash_password, encrypt_secret, create_access_token


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def client_and_db():
    """TestClient wired to an in-memory SQLite DB; yields (client, session)."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = TestSession()

    def _get_db_override():
        try:
            yield session
        finally:
            pass  # keep session open for assertions after requests

    app.dependency_overrides[get_db] = _get_db_override
    with TestClient(app) as c:
        yield c, session
    app.dependency_overrides.clear()
    session.close()
    engine.dispose()


def _make_user(db, email="test@local") -> User:
    u = User(email=email, password_hash=hash_password("pw"))
    db.add(u)
    db.flush()
    return u


def _make_account(db, user_id, label="paper", active=True) -> AlpacaAccount:
    acct = AlpacaAccount(
        user_id=user_id,
        label=label,
        mode="paper",
        api_key="PKTEST",
        api_secret_enc=encrypt_secret("secret"),
        base_url="https://paper-api.alpaca.markets",
        active=active,
    )
    db.add(acct)
    db.flush()
    return acct


def _auth_header(user_id: int) -> dict:
    token = create_access_token({"sub": str(user_id)})
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Bug 1 — _sync_activities failure must not prevent positions/orders sync
# ---------------------------------------------------------------------------

class TestSyncActivitiesIsolation:
    """Activity sync can fail without blocking positions/orders."""

    def test_activities_failure_does_not_block_sync(self, db, demo_account):
        """Even when _sync_activities encounters an error internally,
        positions, orders, and last_sync_at should still be committed."""
        from app.services.sync import sync_account

        mock_client = MagicMock()
        mock_pos = MagicMock()
        mock_pos.symbol = "AAPL"
        mock_pos.qty = "10"
        mock_pos.avg_entry_price = "150"
        mock_pos.market_value = "1800"
        mock_pos.unrealized_pl = "300"
        mock_pos.unrealized_plpc = "0.2"
        mock_pos.current_price = "180"
        mock_client.get_all_positions.return_value = [mock_pos]
        mock_client.get_orders.return_value = []
        mock_client.get_account.return_value = MagicMock(
            equity="10000", cash="2000", long_market_value="8000",
        )
        # Simulate get_account_activities failing (as it does in 0.26.0)
        mock_client.get_account_activities.side_effect = AttributeError(
            "'TradingClient' object has no attribute 'get_account_activities'"
        )

        with patch("app.services.sync.get_trading_client", return_value=mock_client):
            sync_account(db, demo_account)

        # Positions should have been written despite activities failure
        positions = db.execute(
            select(Position).where(Position.account_id == demo_account.id)
        ).scalars().all()
        assert len(positions) == 1
        assert positions[0].symbol == "AAPL"
        assert demo_account.last_sync_at is not None

    def test_sync_activities_catches_import_error(self):
        """_sync_activities catches ImportError from missing class and returns
        gracefully instead of propagating the exception."""
        from app.services.sync import _sync_activities

        mock_db = MagicMock()
        mock_client = MagicMock()
        mock_account = MagicMock()

        import builtins
        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "alpaca.trading.requests":
                # Simulate the module existing but the class not being there
                mod = real_import(name, *args, **kwargs)
                raise ImportError("cannot import name 'GetAccountActivitiesRequest'")
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=fake_import):
            # Should not raise — the try/except inside _sync_activities catches it
            _sync_activities(mock_db, mock_client, mock_account, days=7)


# ---------------------------------------------------------------------------
# Bug 2 — _get_any_account with multiple active accounts
# ---------------------------------------------------------------------------

class TestGetAnyAccountMultiple:
    """_get_any_account must not raise when user has >1 active account."""

    def test_returns_account_when_user_has_multiple(self, client_and_db):
        client, db = client_and_db
        u = _make_user(db)
        acct1 = _make_account(db, u.id, label="paper1")
        acct2 = _make_account(db, u.id, label="paper2")
        db.commit()

        # Hit an endpoint that uses _get_any_account.
        # /market/clock is simplest — doesn't need real Alpaca connection
        # if account exists it tries to call get_market_clock, so we mock it.
        with patch("app.api.market.get_market_clock", return_value={"is_open": False}):
            r = client.get("/api/market/clock", headers=_auth_header(u.id))

        # Before the fix this would 500 with MultipleResultsFound
        assert r.status_code == 200

    def test_returns_none_when_user_has_no_accounts(self, client_and_db):
        client, db = client_and_db
        u = _make_user(db)
        db.commit()

        r = client.get("/api/market/clock", headers=_auth_header(u.id))
        assert r.status_code == 200
        assert r.json()["is_open"] is False


# ---------------------------------------------------------------------------
# Bug 3 — DELETE /api/accounts/<id> auth: can't delete another user's account
# ---------------------------------------------------------------------------

class TestDeleteAccountAuth:
    """DELETE endpoint must only allow deleting own accounts."""

    def test_delete_own_account(self, client_and_db):
        client, db = client_and_db
        u = _make_user(db)
        acct = _make_account(db, u.id)
        db.commit()
        acct_id = acct.id

        r = client.delete(f"/api/accounts/{acct_id}", headers=_auth_header(u.id))
        assert r.status_code == 204

        # Confirm deleted
        remaining = db.execute(
            select(AlpacaAccount).where(AlpacaAccount.id == acct_id)
        ).scalar_one_or_none()
        assert remaining is None

    def test_cannot_delete_other_users_account(self, client_and_db):
        client, db = client_and_db
        u1 = _make_user(db, email="user1@test.co")
        u2 = _make_user(db, email="user2@test.co")
        acct = _make_account(db, u1.id)
        db.commit()

        # u2 tries to delete u1's account — should get 404
        r = client.delete(f"/api/accounts/{acct.id}", headers=_auth_header(u2.id))
        assert r.status_code == 404

        # Account should still exist
        still_there = db.execute(
            select(AlpacaAccount).where(AlpacaAccount.id == acct.id)
        ).scalar_one_or_none()
        assert still_there is not None
