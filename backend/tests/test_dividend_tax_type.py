"""Tests for dividend_tax_type and dividend_tax_notes fields on instruments."""
from __future__ import annotations

from decimal import Decimal
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

from app.db import Base, get_db
from app.main import app
from app.models.instrument import Instrument
from app.models.position import Position
from app.models.user import User
from app.models.account import AlpacaAccount
from app.models import user, account, instrument, position, order, activity, bucket, snapshot, user_goal  # noqa: F401
from app.security import hash_password, encrypt_secret


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


# ── Curated map populates tax fields ─────────────────────────────────────────

def test_backfill_all_sectors_populates_tax_fields(db):
    """backfill_all_sectors writes dividend_tax_type and dividend_tax_notes from curated map."""
    from app.services.sync import backfill_all_sectors

    db.add(Instrument(symbol="SPYI", name="NEOS S&P 500 High Income ETF"))
    db.commit()

    with patch("app.services.yfinance_client.get_ticker_info") as mock_yf, \
         patch("time.sleep"):
        count = backfill_all_sectors(db)

    mock_yf.assert_not_called()
    assert count == 1

    inst = db.get(Instrument, "SPYI")
    assert inst.dividend_tax_type == "Section 1256 (60/40)"
    assert inst.dividend_tax_notes == "S&P 500 index options under Section 1256; very tax-efficient distributions"


def test_backfill_sectors_populates_tax_fields(db):
    """_backfill_sectors writes dividend_tax_type and dividend_tax_notes from curated map."""
    from app.services.sync import _backfill_sectors

    inst = Instrument(symbol="SGOV", name="iShares Treasury")
    db.add(inst)
    db.commit()

    with patch("app.services.yfinance_client.get_ticker_info") as mock_yf, \
         patch("time.sleep"):
        _backfill_sectors(db, ["SGOV"])

    mock_yf.assert_not_called()

    refreshed = db.get(Instrument, "SGOV")
    assert refreshed.dividend_tax_type == "Treasury (state-exempt)"
    assert refreshed.dividend_tax_notes == "US Treasury interest: federally taxable as ordinary, exempt from state/local tax"


def test_non_curated_symbol_has_no_tax_fields(db):
    """Symbols not in curated map have NULL dividend_tax_type after classification."""
    from app.services.sync import backfill_all_sectors

    SAMPLE_YFINANCE_EQUITY = {
        "quoteType": "EQUITY",
        "category": None,
        "fundFamily": None,
        "longName": "Apple Inc.",
        "sector": "Technology",
        "industry": "Consumer Electronics",
    }

    db.add(Instrument(symbol="AAPL", name="Apple"))
    db.commit()

    with patch("app.services.yfinance_client.get_ticker_info", return_value=SAMPLE_YFINANCE_EQUITY), \
         patch("time.sleep"):
        backfill_all_sectors(db)

    inst = db.get(Instrument, "AAPL")
    assert inst.dividend_tax_type is None
    assert inst.dividend_tax_notes is None


# ── Holdings endpoint returns tax fields ─────────────────────────────────────

def test_holdings_endpoint_returns_tax_fields():
    """GET /api/holdings includes dividend_tax_type and dividend_tax_notes."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    session = Session()
    u = User(email="tax@test.co", password_hash=hash_password("pw"))
    session.add(u)
    session.flush()

    acct = AlpacaAccount(
        user_id=u.id, label="paper", mode="paper",
        api_key="PKTEST", api_secret_enc=encrypt_secret("secret"),
        base_url="https://paper-api.alpaca.markets", active=True,
    )
    session.add(acct)
    session.flush()

    session.add(Instrument(
        symbol="SPYI", name="NEOS S&P 500 High Income ETF",
        sector="Diversified", dividend_tax_type="Section 1256 (60/40)",
        dividend_tax_notes="S&P 500 index options under Section 1256; very tax-efficient distributions",
    ))
    session.add(Instrument(
        symbol="AAPL", name="Apple", sector="Technology",
    ))
    session.flush()

    session.add(Position(
        account_id=acct.id, symbol="SPYI", qty=Decimal("100"),
        market_value=Decimal("5000"), avg_entry_price=Decimal("50"),
    ))
    session.add(Position(
        account_id=acct.id, symbol="AAPL", qty=Decimal("10"),
        market_value=Decimal("2000"), avg_entry_price=Decimal("150"),
    ))
    session.commit()
    account_id = acct.id
    session.close()

    def _get_db_override():
        s = Session()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = _get_db_override

    with TestClient(app) as c:
        c.post("/api/auth/register", json={"email": "tax@test.co", "password": "pw"})
        r = c.post("/api/auth/login", json={"email": "tax@test.co", "password": "pw"})
        token = r.json()["access_token"]

        r = c.get(
            "/api/holdings",
            params={"account_id": account_id},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        data = r.json()

        spyi = next(h for h in data if h["symbol"] == "SPYI")
        assert spyi["dividend_tax_type"] == "Section 1256 (60/40)"
        assert spyi["dividend_tax_notes"] == "S&P 500 index options under Section 1256; very tax-efficient distributions"

        aapl = next(h for h in data if h["symbol"] == "AAPL")
        assert aapl["dividend_tax_type"] is None
        assert aapl["dividend_tax_notes"] is None

    app.dependency_overrides.clear()
    engine.dispose()
