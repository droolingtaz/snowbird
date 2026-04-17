"""Tests for GET /api/portfolio/summary — PL calculations."""
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.main import app
from app.models import user, account, instrument, position, order, activity, bucket, snapshot  # noqa: F401
from app.security import hash_password, encrypt_secret


@pytest.fixture()
def client_and_account():
    """TestClient with a seeded user + account; yields (client, account_id, token)."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def _get_db_override():
        s = TestSession()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = _get_db_override
    with TestClient(app) as c:
        # Register + login
        c.post("/api/auth/register", json={"email": "port@test.co", "password": "pw123456"})
        r = c.post("/api/auth/login", json={"email": "port@test.co", "password": "pw123456"})
        token = r.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Create an Alpaca account via the DB
        s = next(_get_db_override())
        from app.models.user import User
        from app.models.account import AlpacaAccount

        u = s.query(User).filter_by(email="port@test.co").first()
        acct = AlpacaAccount(
            user_id=u.id,
            label="paper",
            mode="paper",
            api_key="PKTEST",
            api_secret_enc=encrypt_secret("secret"),
            base_url="https://paper-api.alpaca.markets",
            active=True,
        )
        s.add(acct)
        s.commit()
        account_id = acct.id
        s.close()

        yield c, account_id, headers

    app.dependency_overrides.clear()
    engine.dispose()


def _mock_alpaca_account(equity="105150.93", last_equity="104234.87",
                         cash="-51.96", buying_power="200000.00",
                         long_market_value="105202.89"):
    """Return a mock that behaves like alpaca-py TradeAccount."""
    mock = MagicMock()
    mock.equity = equity
    mock.last_equity = last_equity
    mock.cash = cash
    mock.buying_power = buying_power
    mock.long_market_value = long_market_value
    # Ensure the mock does NOT have equity_previous_close —
    # accessing it should raise AttributeError just like the real model.
    del mock.equity_previous_close
    return mock


@patch("app.api.portfolio.get_trading_client", create=True)
@patch("app.services.alpaca.get_trading_client")
def test_portfolio_summary_today_pl(mock_svc, mock_api, client_and_account):
    """today_pl should equal equity − last_equity, not zero."""
    c, account_id, headers = client_and_account

    fake_account = _mock_alpaca_account()
    mock_client = MagicMock()
    mock_client.get_account.return_value = fake_account
    mock_svc.return_value = mock_client
    mock_api.return_value = mock_client

    r = c.get(f"/api/portfolio/summary?account_id={account_id}", headers=headers)
    assert r.status_code == 200, r.text
    data = r.json()

    expected_today_pl = 105150.93 - 104234.87  # 916.06
    assert abs(data["today_pl"] - expected_today_pl) < 0.01, (
        f"today_pl should be ~{expected_today_pl}, got {data['today_pl']}"
    )
    assert data["today_pl"] != 0.0, "today_pl must not be zero-defaulted"


@patch("app.api.portfolio.get_trading_client", create=True)
@patch("app.services.alpaca.get_trading_client")
def test_portfolio_summary_total_pl(mock_svc, mock_api, client_and_account):
    """total_pl = equity − cash − total_cost. With no positions, total_cost=0."""
    c, account_id, headers = client_and_account

    fake_account = _mock_alpaca_account()
    mock_client = MagicMock()
    mock_client.get_account.return_value = fake_account
    mock_svc.return_value = mock_client
    mock_api.return_value = mock_client

    r = c.get(f"/api/portfolio/summary?account_id={account_id}", headers=headers)
    assert r.status_code == 200, r.text
    data = r.json()

    # total_pl = equity - cash - total_cost; no positions → total_cost = 0
    expected_total_pl = 105150.93 - (-51.96) - 0  # 105202.89
    assert abs(data["total_pl"] - expected_total_pl) < 0.01, (
        f"total_pl should be ~{expected_total_pl}, got {data['total_pl']}"
    )
    assert data["total_pl"] != 0.0, "total_pl must not be zero-defaulted"


@patch("app.api.portfolio.get_trading_client", create=True)
@patch("app.services.alpaca.get_trading_client")
def test_portfolio_summary_today_pl_pct(mock_svc, mock_api, client_and_account):
    """today_pl_pct = today_pl / prev_equity * 100."""
    c, account_id, headers = client_and_account

    fake_account = _mock_alpaca_account()
    mock_client = MagicMock()
    mock_client.get_account.return_value = fake_account
    mock_svc.return_value = mock_client
    mock_api.return_value = mock_client

    r = c.get(f"/api/portfolio/summary?account_id={account_id}", headers=headers)
    assert r.status_code == 200, r.text
    data = r.json()

    expected_pct = (105150.93 - 104234.87) / 104234.87 * 100  # ~0.8789
    assert abs(data["today_pl_pct"] - expected_pct) < 0.01
