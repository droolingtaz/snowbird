"""Tests for Finnhub company profile integration and allocation-by-sector."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import patch, MagicMock

import pytest
from sqlalchemy import create_engine, select
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


@pytest.fixture()
def demo_account(db):
    u = User(email="t@local", password_hash=hash_password("pw"))
    db.add(u)
    db.flush()

    acct = AlpacaAccount(
        user_id=u.id,
        label="paper",
        mode="paper",
        api_key="PKTEST",
        api_secret_enc=encrypt_secret("secret"),
        base_url="https://paper-api.alpaca.markets",
        active=True,
    )
    db.add(acct)
    db.commit()
    return acct


# ── Finnhub get_company_profile ──────────────────────────────────────────────

SAMPLE_PROFILE = {
    "country": "US",
    "currency": "USD",
    "exchange": "NASDAQ NMS - GLOBAL MARKET",
    "finnhubIndustry": "Technology",
    "ipo": "1980-12-12",
    "logo": "https://example.com/logo.png",
    "marketCapitalization": 2800000,
    "name": "Apple Inc",
    "phone": "14089961010",
    "shareOutstanding": 15700,
    "ticker": "AAPL",
    "weburl": "https://www.apple.com/",
}


def test_get_company_profile_returns_dict():
    """get_company_profile returns parsed profile dict on success."""
    import app.services.finnhub as fh

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = SAMPLE_PROFILE

    with patch.object(fh, "settings") as mock_settings, \
         patch("httpx.get", return_value=mock_resp):
        mock_settings.FINNHUB_API_KEY = "test-key"
        result = fh.get_company_profile("AAPL")

    assert result is not None
    assert result["finnhubIndustry"] == "Technology"
    assert result["name"] == "Apple Inc"


def test_get_company_profile_returns_none_without_key():
    """get_company_profile returns None when API key is missing."""
    import app.services.finnhub as fh

    with patch.object(fh, "settings") as mock_settings:
        mock_settings.FINNHUB_API_KEY = None
        result = fh.get_company_profile("AAPL")

    assert result is None


def test_get_company_profile_handles_rate_limit():
    """get_company_profile retries on 429 then succeeds."""
    import app.services.finnhub as fh

    rate_limit_resp = MagicMock()
    rate_limit_resp.status_code = 429

    ok_resp = MagicMock()
    ok_resp.status_code = 200
    ok_resp.json.return_value = SAMPLE_PROFILE

    with patch.object(fh, "settings") as mock_settings, \
         patch("httpx.get", side_effect=[rate_limit_resp, ok_resp]), \
         patch("time.sleep"):
        mock_settings.FINNHUB_API_KEY = "test-key"
        result = fh.get_company_profile("AAPL")

    assert result is not None
    assert result["finnhubIndustry"] == "Technology"


def test_get_company_profile_returns_none_on_http_error():
    """get_company_profile returns None on non-429 HTTP error."""
    import httpx
    import app.services.finnhub as fh

    error_resp = MagicMock()
    error_resp.status_code = 500
    error_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
        "Server Error", request=MagicMock(), response=error_resp,
    )

    with patch.object(fh, "settings") as mock_settings, \
         patch("httpx.get", return_value=error_resp):
        mock_settings.FINNHUB_API_KEY = "test-key"
        result = fh.get_company_profile("AAPL")

    assert result is None


# ── _backfill_sectors ─────────────────────────────────────────────────────────

def test_backfill_sectors_updates_instrument(db):
    """_backfill_sectors writes sector from Finnhub profile to instrument row."""
    from app.services.sync import _backfill_sectors

    inst = Instrument(symbol="AAPL", name="Apple", asset_class="us_equity")
    db.add(inst)
    db.commit()

    with patch("app.services.finnhub.get_company_profile", return_value=SAMPLE_PROFILE), \
         patch("time.sleep"):
        _backfill_sectors(db, ["AAPL"])

    refreshed = db.get(Instrument, "AAPL")
    assert refreshed.sector == "Technology"


def test_backfill_sectors_skips_existing_sector(db):
    """_backfill_sectors does not call Finnhub for instruments that already have sector."""
    from app.services.sync import _backfill_sectors

    inst = Instrument(symbol="MSFT", name="Microsoft", sector="Technology")
    db.add(inst)
    db.commit()

    with patch("app.services.finnhub.get_company_profile") as mock_profile, \
         patch("time.sleep"):
        _backfill_sectors(db, ["MSFT"])

    mock_profile.assert_not_called()


def test_backfill_sectors_handles_none_profile(db):
    """_backfill_sectors gracefully handles None profile (API error)."""
    from app.services.sync import _backfill_sectors

    inst = Instrument(symbol="XYZ", name="XYZ Corp")
    db.add(inst)
    db.commit()

    with patch("app.services.finnhub.get_company_profile", return_value=None), \
         patch("time.sleep"):
        _backfill_sectors(db, ["XYZ"])

    refreshed = db.get(Instrument, "XYZ")
    assert refreshed.sector is None


# ── backfill_all_sectors (CLI helper) ─────────────────────────────────────────

def test_backfill_all_sectors_updates_count(db):
    """backfill_all_sectors returns count of updated instruments."""
    from app.services.sync import backfill_all_sectors

    db.add(Instrument(symbol="AAPL", name="Apple"))
    db.add(Instrument(symbol="GOOG", name="Google", sector="Technology"))
    db.commit()

    profiles = {"AAPL": SAMPLE_PROFILE, "GOOG": SAMPLE_PROFILE}

    with patch("app.services.finnhub.get_company_profile", side_effect=lambda s: profiles.get(s)), \
         patch("time.sleep"):
        count = backfill_all_sectors(db)

    assert count == 1  # only AAPL updated, GOOG skipped
    assert db.get(Instrument, "AAPL").sector == "Technology"


# ── Allocation endpoint with sectors ──────────────────────────────────────────

@pytest.fixture()
def client_with_data():
    """TestClient with seeded positions and instruments."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    # Seed data
    session = Session()
    u = User(email="alloc@test.co", password_hash=hash_password("pw"))
    session.add(u)
    session.flush()

    acct = AlpacaAccount(
        user_id=u.id,
        label="paper",
        mode="paper",
        api_key="PKTEST",
        api_secret_enc=encrypt_secret("secret"),
        base_url="https://paper-api.alpaca.markets",
        active=True,
    )
    session.add(acct)
    session.flush()

    # Add instruments with sectors
    session.add(Instrument(symbol="AAPL", name="Apple", sector="Technology"))
    session.add(Instrument(symbol="JNJ", name="J&J", sector="Healthcare"))
    session.flush()

    # Add positions
    session.add(Position(
        account_id=acct.id, symbol="AAPL", qty=Decimal("10"),
        market_value=Decimal("2000"), avg_entry_price=Decimal("150"),
    ))
    session.add(Position(
        account_id=acct.id, symbol="JNJ", qty=Decimal("5"),
        market_value=Decimal("1000"), avg_entry_price=Decimal("160"),
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

    # Login
    with TestClient(app) as c:
        c.post("/api/auth/register", json={"email": "alloc@test.co", "password": "pw"})
        r = c.post("/api/auth/login", json={"email": "alloc@test.co", "password": "pw"})
        token = r.json()["access_token"]
        yield c, token, account_id

    app.dependency_overrides.clear()
    engine.dispose()


def test_allocation_groups_by_sector(client_with_data):
    """GET /api/portfolio/allocation?by=sector returns grouped sectors, not 100% Unknown."""
    c, token, account_id = client_with_data
    r = c.get(
        "/api/portfolio/allocation",
        params={"account_id": account_id, "by": "sector"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    data = r.json()
    labels = [item["label"] for item in data["items"]]
    assert "Technology" in labels
    assert "Healthcare" in labels
    assert "Unknown" not in labels


def test_allocation_unknown_when_no_sector():
    """Allocation falls back to 'Unknown' for instruments without sector."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    session = Session()
    u = User(email="unk@test.co", password_hash=hash_password("pw"))
    session.add(u)
    session.flush()

    acct = AlpacaAccount(
        user_id=u.id, label="paper", mode="paper",
        api_key="PKTEST", api_secret_enc=encrypt_secret("secret"),
        base_url="https://paper-api.alpaca.markets", active=True,
    )
    session.add(acct)
    session.flush()

    # AAPL has no sector, JNJ has one
    session.add(Instrument(symbol="AAPL", name="Apple", sector=None))
    session.add(Instrument(symbol="JNJ", name="J&J", sector="Healthcare"))
    session.flush()
    session.add(Position(
        account_id=acct.id, symbol="AAPL", qty=Decimal("10"),
        market_value=Decimal("2000"), avg_entry_price=Decimal("150"),
    ))
    session.add(Position(
        account_id=acct.id, symbol="JNJ", qty=Decimal("5"),
        market_value=Decimal("1000"), avg_entry_price=Decimal("160"),
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
        c.post("/api/auth/register", json={"email": "unk@test.co", "password": "pw"})
        r = c.post("/api/auth/login", json={"email": "unk@test.co", "password": "pw"})
        token = r.json()["access_token"]

        r = c.get(
            "/api/portfolio/allocation",
            params={"account_id": account_id, "by": "sector"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        data = r.json()
        labels = [item["label"] for item in data["items"]]
        assert "Unknown" in labels
        assert "Healthcare" in labels

    app.dependency_overrides.clear()
    engine.dispose()
