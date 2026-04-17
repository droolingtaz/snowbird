"""Tests for instrument classification (yfinance + Finnhub fallback) and allocation endpoints."""
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


# ── Sample data ──────────────────────────────────────────────────────────────

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

SAMPLE_YFINANCE_ETF = {
    "quoteType": "ETF",
    "category": "Derivative Income",
    "fundFamily": "Neos",
    "longName": "NEOS S&P 500 High Income ETF",
    "sector": None,
    "industry": None,
}

SAMPLE_YFINANCE_EQUITY = {
    "quoteType": "EQUITY",
    "category": None,
    "fundFamily": None,
    "longName": "Apple Inc.",
    "sector": "Technology",
    "industry": "Consumer Electronics",
}

SAMPLE_YFINANCE_TREASURY_ETF = {
    "quoteType": "ETF",
    "category": "Short Government",
    "fundFamily": "iShares",
    "longName": "iShares 0-3 Month Treasury Bond ETF",
    "sector": None,
    "industry": None,
}

SAMPLE_YFINANCE_CRYPTO_ETF = {
    "quoteType": "ETF",
    "category": "Digital Assets",
    "fundFamily": "ProShares",
    "longName": "ProShares Bitcoin Strategy ETF",
    "sector": None,
    "industry": None,
}

SAMPLE_YFINANCE_REAL_ESTATE_ETF = {
    "quoteType": "ETF",
    "category": "Real Estate",
    "fundFamily": "Vanguard",
    "longName": "Vanguard Real Estate ETF",
    "sector": None,
    "industry": None,
}

SAMPLE_YFINANCE_COMMODITY_ETF = {
    "quoteType": "ETF",
    "category": "Commodities Focused",
    "fundFamily": "SPDR",
    "longName": "SPDR Gold Shares",
    "sector": None,
    "industry": None,
}


# ── Finnhub get_company_profile ──────────────────────────────────────────────

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
    """_backfill_sectors writes sector from yfinance to instrument row."""
    from app.services.sync import _backfill_sectors

    inst = Instrument(symbol="AAPL", name="Apple", asset_class="us_equity")
    db.add(inst)
    db.commit()

    with patch("app.services.yfinance_client.get_ticker_info", return_value=SAMPLE_YFINANCE_EQUITY), \
         patch("time.sleep"):
        _backfill_sectors(db, ["AAPL"])

    refreshed = db.get(Instrument, "AAPL")
    assert refreshed.sector == "Technology"


def test_backfill_sectors_skips_existing_sector(db):
    """_backfill_sectors does not call yfinance for instruments that already have sector."""
    from app.services.sync import _backfill_sectors

    inst = Instrument(symbol="MSFT", name="Microsoft", sector="Technology")
    db.add(inst)
    db.commit()

    with patch("app.services.yfinance_client.get_ticker_info") as mock_yf, \
         patch("time.sleep"):
        _backfill_sectors(db, ["MSFT"])

    mock_yf.assert_not_called()


def test_backfill_sectors_handles_none_info(db):
    """_backfill_sectors gracefully handles None from yfinance."""
    from app.services.sync import _backfill_sectors

    inst = Instrument(symbol="XYZ", name="XYZ Corp")
    db.add(inst)
    db.commit()

    with patch("app.services.yfinance_client.get_ticker_info", return_value=None), \
         patch("app.services.finnhub.get_company_profile", return_value=None), \
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

    with patch("app.services.yfinance_client.get_ticker_info", return_value=SAMPLE_YFINANCE_EQUITY), \
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


# ── yfinance_client unit tests ──────────────────────────────────────────────

def test_derive_asset_class_etf_equity():
    """ETF with generic category defaults to Equity asset class."""
    from app.services.yfinance_client import derive_asset_class
    assert derive_asset_class("ETF", "Derivative Income") == "Equity"


def test_derive_asset_class_etf_fixed_income():
    """ETF with treasury/bond category → Fixed Income."""
    from app.services.yfinance_client import derive_asset_class
    assert derive_asset_class("ETF", "Short Government") == "Fixed Income"
    assert derive_asset_class("ETF", "Long-Term Treasury") == "Fixed Income"
    assert derive_asset_class("ETF", "Corporate Bond") == "Fixed Income"


def test_derive_asset_class_etf_crypto():
    """ETF with crypto/digital category → Crypto."""
    from app.services.yfinance_client import derive_asset_class
    assert derive_asset_class("ETF", "Digital Assets") == "Crypto"
    assert derive_asset_class("ETF", "Crypto") == "Crypto"


def test_derive_asset_class_etf_real_estate():
    """ETF with real estate/REIT category → Real Estate."""
    from app.services.yfinance_client import derive_asset_class
    assert derive_asset_class("ETF", "Real Estate") == "Real Estate"
    assert derive_asset_class("ETF", "REIT") == "Real Estate"


def test_derive_asset_class_etf_commodities():
    """ETF with commodity category → Commodities."""
    from app.services.yfinance_client import derive_asset_class
    assert derive_asset_class("ETF", "Commodities Focused") == "Commodities"
    assert derive_asset_class("ETF", "Gold") == "Commodities"


def test_derive_asset_class_equity():
    """EQUITY quoteType → Equity."""
    from app.services.yfinance_client import derive_asset_class
    assert derive_asset_class("EQUITY", None) == "Equity"
    assert derive_asset_class("EQUITY", "something") == "Equity"


def test_derive_asset_class_unknown():
    """Unknown quoteType → Other."""
    from app.services.yfinance_client import derive_asset_class
    assert derive_asset_class(None, None) == "Other"
    assert derive_asset_class("MUTUALFUND", "Some Category") == "Other"


def test_get_ticker_info_returns_dict():
    """get_ticker_info returns parsed info dict on success."""
    from app.services.yfinance_client import get_ticker_info

    mock_info = {
        "quoteType": "ETF",
        "category": "Derivative Income",
        "fundFamily": "Neos",
        "longName": "NEOS S&P 500 High Income ETF",
        "sector": None,
        "sectorDisp": None,
        "industry": None,
        "industryDisp": None,
    }

    mock_ticker = MagicMock()
    mock_ticker.info = mock_info

    with patch("app.services.yfinance_client._cache_get", return_value=None), \
         patch("app.services.yfinance_client._cache_set"), \
         patch("yfinance.Ticker", return_value=mock_ticker):
        result = get_ticker_info("SPYI")

    assert result is not None
    assert result["quoteType"] == "ETF"
    assert result["category"] == "Derivative Income"
    assert result["longName"] == "NEOS S&P 500 High Income ETF"


def test_get_ticker_info_returns_cached():
    """get_ticker_info returns cached result when available."""
    from app.services.yfinance_client import get_ticker_info

    cached = {"quoteType": "ETF", "category": "Equity Income"}

    with patch("app.services.yfinance_client._cache_get", return_value=cached):
        result = get_ticker_info("SPYI")

    assert result == cached


def test_get_ticker_info_handles_exception():
    """get_ticker_info returns None on yfinance exception."""
    from app.services.yfinance_client import get_ticker_info

    with patch("app.services.yfinance_client._cache_get", return_value=None), \
         patch("yfinance.Ticker", side_effect=Exception("network error")):
        result = get_ticker_info("FAIL")

    assert result is None


def test_get_ticker_info_returns_none_on_empty_info():
    """get_ticker_info returns None when yfinance returns empty/missing quoteType."""
    from app.services.yfinance_client import get_ticker_info

    mock_ticker = MagicMock()
    mock_ticker.info = {"quoteType": None}

    with patch("app.services.yfinance_client._cache_get", return_value=None), \
         patch("yfinance.Ticker", return_value=mock_ticker):
        result = get_ticker_info("EMPTY")

    assert result is None


# ── _classify_instrument (yfinance primary + Finnhub fallback) ──────────────

def test_classify_etf_via_yfinance(db):
    """ETF classified via yfinance sets is_etf, etf_category, asset_class, sector."""
    from app.services.sync import _classify_instrument

    inst = Instrument(symbol="SPYI", name="NEOS S&P 500 High Income ETF")
    db.add(inst)
    db.commit()

    mock_time = MagicMock()

    with patch("app.services.yfinance_client.get_ticker_info", return_value=SAMPLE_YFINANCE_ETF):
        changed = _classify_instrument(inst, _time_module=mock_time)

    assert changed is True
    assert inst.is_etf is True
    assert inst.etf_category == "Derivative Income"
    assert inst.asset_class == "Equity"
    assert inst.name == "NEOS S&P 500 High Income ETF"


def test_classify_equity_via_yfinance(db):
    """Equity classified via yfinance sets sector, industry, is_etf=False."""
    from app.services.sync import _classify_instrument

    inst = Instrument(symbol="AAPL", name="Apple", asset_class="us_equity")
    db.add(inst)
    db.commit()

    mock_time = MagicMock()

    with patch("app.services.yfinance_client.get_ticker_info", return_value=SAMPLE_YFINANCE_EQUITY), \
         patch("app.services.finnhub.get_company_profile") as mock_fh:
        changed = _classify_instrument(inst, _time_module=mock_time)

    assert changed is True
    assert inst.sector == "Technology"
    assert inst.industry == "Consumer Electronics"
    assert inst.is_etf is False
    assert inst.asset_class == "Equity"
    # Finnhub should NOT have been called since yfinance succeeded
    mock_fh.assert_not_called()


def test_classify_treasury_etf_via_yfinance(db):
    """Treasury ETF gets asset_class=Fixed Income."""
    from app.services.sync import _classify_instrument

    inst = Instrument(symbol="SGOV", name="iShares 0-3 Month Treasury Bond ETF")
    db.add(inst)
    db.commit()

    mock_time = MagicMock()

    with patch("app.services.yfinance_client.get_ticker_info", return_value=SAMPLE_YFINANCE_TREASURY_ETF):
        changed = _classify_instrument(inst, _time_module=mock_time)

    assert changed is True
    assert inst.is_etf is True
    assert inst.etf_category == "Short Government"
    assert inst.asset_class == "Fixed Income"
    assert inst.sector == "Fixed Income"


def test_classify_crypto_etf_via_yfinance(db):
    """Crypto ETF gets asset_class=Crypto."""
    from app.services.sync import _classify_instrument

    inst = Instrument(symbol="BTCI", name="Bitcoin ETF")
    db.add(inst)
    db.commit()

    mock_time = MagicMock()

    with patch("app.services.yfinance_client.get_ticker_info", return_value=SAMPLE_YFINANCE_CRYPTO_ETF):
        changed = _classify_instrument(inst, _time_module=mock_time)

    assert changed is True
    assert inst.is_etf is True
    assert inst.asset_class == "Crypto"
    assert inst.sector == "Crypto"


def test_classify_real_estate_etf_via_yfinance(db):
    """Real Estate ETF gets asset_class=Real Estate."""
    from app.services.sync import _classify_instrument

    inst = Instrument(symbol="VNQ", name="Vanguard Real Estate ETF")
    db.add(inst)
    db.commit()

    mock_time = MagicMock()

    with patch("app.services.yfinance_client.get_ticker_info", return_value=SAMPLE_YFINANCE_REAL_ESTATE_ETF):
        changed = _classify_instrument(inst, _time_module=mock_time)

    assert changed is True
    assert inst.is_etf is True
    assert inst.asset_class == "Real Estate"
    assert inst.sector == "Real Estate"


def test_classify_commodity_etf_via_yfinance(db):
    """Commodity ETF gets asset_class=Commodities."""
    from app.services.sync import _classify_instrument

    inst = Instrument(symbol="GLD", name="SPDR Gold Shares")
    db.add(inst)
    db.commit()

    mock_time = MagicMock()

    with patch("app.services.yfinance_client.get_ticker_info", return_value=SAMPLE_YFINANCE_COMMODITY_ETF):
        changed = _classify_instrument(inst, _time_module=mock_time)

    assert changed is True
    assert inst.is_etf is True
    assert inst.asset_class == "Commodities"
    assert inst.sector == "Commodities"


def test_classify_falls_back_to_finnhub_on_yfinance_failure(db):
    """When yfinance returns None, falls back to Finnhub stock/profile2."""
    from app.services.sync import _classify_instrument

    inst = Instrument(symbol="AAPL", name="Apple", asset_class="us_equity")
    db.add(inst)
    db.commit()

    mock_time = MagicMock()

    with patch("app.services.yfinance_client.get_ticker_info", return_value=None), \
         patch("app.services.finnhub.get_company_profile", return_value=SAMPLE_PROFILE):
        changed = _classify_instrument(inst, _time_module=mock_time)

    assert changed is True
    assert inst.sector == "Technology"
    assert inst.is_etf is False
    assert inst.asset_class == "Equity"


def test_classify_nothing_when_all_fail(db):
    """Instrument left unchanged when both yfinance and Finnhub return nothing."""
    from app.services.sync import _classify_instrument

    inst = Instrument(symbol="ZZZZ", name="Unknown")
    db.add(inst)
    db.commit()

    mock_time = MagicMock()

    with patch("app.services.yfinance_client.get_ticker_info", return_value=None), \
         patch("app.services.finnhub.get_company_profile", return_value=None):
        changed = _classify_instrument(inst, _time_module=mock_time)

    assert changed is False
    assert inst.sector is None
    assert inst.is_etf is not True
    assert inst.etf_category is None


def test_classify_etf_diversified_when_no_category_match(db):
    """ETF with a category that doesn't match any keyword gets sector=Diversified."""
    from app.services.sync import _classify_instrument

    info = {
        "quoteType": "ETF",
        "category": "Covered Call",
        "fundFamily": "Some Fund",
        "longName": "Some Covered Call ETF",
        "sector": None,
        "industry": None,
    }

    inst = Instrument(symbol="XYLD", name="Covered Call ETF")
    db.add(inst)
    db.commit()

    mock_time = MagicMock()

    with patch("app.services.yfinance_client.get_ticker_info", return_value=info):
        changed = _classify_instrument(inst, _time_module=mock_time)

    assert changed is True
    assert inst.is_etf is True
    assert inst.sector == "Diversified"
    assert inst.asset_class == "Equity"


# ── backfill_all_sectors with ETFs ───────────────────────────────────────────

def test_backfill_all_sectors_classifies_etf(db):
    """backfill_all_sectors handles ETFs via curated map (SPYI is curated)."""
    from app.services.sync import backfill_all_sectors

    db.add(Instrument(symbol="SPYI", name="NEOS S&P 500 High Income ETF"))
    db.add(Instrument(symbol="AAPL", name="Apple", sector="Technology"))
    db.commit()

    with patch("app.services.yfinance_client.get_ticker_info", return_value=SAMPLE_YFINANCE_ETF), \
         patch("time.sleep"):
        count = backfill_all_sectors(db)

    assert count == 1  # only SPYI, AAPL skipped (has sector)
    spyi = db.get(Instrument, "SPYI")
    assert spyi.is_etf is True
    assert spyi.etf_category == "S&P 500 / Covered Call"  # from curated map


# ── Allocation endpoint with ETF category ────────────────────────────────────

def test_allocation_groups_by_etf_category(client_with_data):
    """GET /api/portfolio/allocation?by=etf_category groups by ETF category."""
    c, token, account_id = client_with_data

    # The seeded instruments don't have etf_category, so they should show as Unknown
    r = c.get(
        "/api/portfolio/allocation",
        params={"account_id": account_id, "by": "etf_category"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    data = r.json()
    labels = [item["label"] for item in data["items"]]
    assert "Unknown" in labels


def test_allocation_groups_by_asset_class(client_with_data):
    """GET /api/portfolio/allocation?by=asset_class groups by asset class."""
    c, token, account_id = client_with_data

    r = c.get(
        "/api/portfolio/allocation",
        params={"account_id": account_id, "by": "asset_class"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    data = r.json()
    # Should return items (might be "Unknown" since seed data has no asset_class set)
    assert len(data["items"]) > 0


# ── yfinance throttle + retry tests ────────────────────────────────────────

def test_get_ticker_info_retries_on_429_then_succeeds():
    """get_ticker_info retries on 429 errors and returns data on eventual success."""
    from app.services.yfinance_client import get_ticker_info

    expected = {
        "quoteType": "ETF",
        "category": "Derivative Income",
        "fundFamily": "Neos",
        "longName": "NEOS S&P 500 High Income ETF",
        "sector": None,
        "industry": None,
    }

    call_count = 0

    def _fake_fetch(symbol):
        nonlocal call_count
        call_count += 1
        if call_count <= 2:
            raise Exception("HTTPError 429 Too Many Requests")
        return expected

    sleep_calls = []

    with patch("app.services.yfinance_client._cache_get", return_value=None), \
         patch("app.services.yfinance_client._cache_set"):
        result = get_ticker_info(
            "SPYI",
            _sleep_fn=lambda s: sleep_calls.append(s),
            _fetch_fn=_fake_fetch,
        )

    assert result == expected
    assert call_count == 3  # 2 failures + 1 success
    # First call is the per-call throttle sleep, then 2 backoff sleeps
    assert len(sleep_calls) == 3  # throttle + 2 retries


def test_get_ticker_info_gives_up_after_max_retries():
    """get_ticker_info returns None after exhausting retries on persistent 429."""
    from app.services.yfinance_client import get_ticker_info

    call_count = 0

    def _fake_fetch(symbol):
        nonlocal call_count
        call_count += 1
        raise Exception("429 Too Many Requests")

    with patch("app.services.yfinance_client._cache_get", return_value=None):
        result = get_ticker_info(
            "FAIL",
            _sleep_fn=lambda s: None,
            _fetch_fn=_fake_fetch,
        )

    assert result is None
    assert call_count == 5  # YFINANCE_MAX_RETRIES default


def test_get_ticker_info_no_retry_on_non_retryable():
    """get_ticker_info does not retry on non-retryable errors (e.g. KeyError)."""
    from app.services.yfinance_client import get_ticker_info

    call_count = 0

    def _fake_fetch(symbol):
        nonlocal call_count
        call_count += 1
        raise KeyError("some_key")

    with patch("app.services.yfinance_client._cache_get", return_value=None):
        result = get_ticker_info(
            "FAIL",
            _sleep_fn=lambda s: None,
            _fetch_fn=_fake_fetch,
        )

    assert result is None
    assert call_count == 1  # no retries


def test_get_ticker_info_throttle_sleep():
    """get_ticker_info calls sleep for per-call throttle before fetching."""
    from app.services.yfinance_client import get_ticker_info

    expected = {"quoteType": "ETF", "category": "Test", "fundFamily": None,
                "longName": None, "sector": None, "industry": None}

    sleep_calls = []

    with patch("app.services.yfinance_client._cache_get", return_value=None), \
         patch("app.services.yfinance_client._cache_set"):
        result = get_ticker_info(
            "TEST",
            _sleep_fn=lambda s: sleep_calls.append(s),
            _fetch_fn=lambda sym: expected,
        )

    assert result == expected
    # At least the throttle sleep should have been called
    assert len(sleep_calls) >= 1
    # First sleep should be the per-call throttle (default 7s)
    from app.services.yfinance_client import YFINANCE_PER_CALL_SLEEP
    assert sleep_calls[0] == YFINANCE_PER_CALL_SLEEP


def test_is_retryable_detects_429():
    """_is_retryable returns True for 429 and timeout errors."""
    from app.services.yfinance_client import _is_retryable

    assert _is_retryable(Exception("HTTPError 429 Too Many Requests")) is True
    assert _is_retryable(Exception("rate limit exceeded")) is True
    assert _is_retryable(Exception("Connection timed out")) is True
    assert _is_retryable(Exception("ConnectionError: reset")) is True
    assert _is_retryable(KeyError("some_key")) is False
    assert _is_retryable(ValueError("bad value")) is False


# ── backfill_all_sectors resilience ────────────────────────────────────────

def test_backfill_all_sectors_continues_on_symbol_failure(db):
    """backfill_all_sectors logs warning and continues when one symbol raises."""
    from app.services.sync import backfill_all_sectors

    db.add(Instrument(symbol="FAIL", name="Failure"))
    db.add(Instrument(symbol="AAPL", name="Apple"))
    db.commit()

    call_count = 0

    def _mock_get_ticker_info(symbol):
        nonlocal call_count
        call_count += 1
        if symbol == "FAIL":
            raise RuntimeError("simulated crash")
        return SAMPLE_YFINANCE_EQUITY

    with patch("app.services.yfinance_client.get_ticker_info", side_effect=_mock_get_ticker_info), \
         patch("app.services.finnhub.get_company_profile", return_value=None), \
         patch("time.sleep"):
        count = backfill_all_sectors(db)

    # AAPL should have been classified despite FAIL raising
    assert count == 1
    assert db.get(Instrument, "AAPL").sector == "Technology"


# ── Backward compat alias ───────────────────────────────────────────────────

def test_classify_instrument_via_finnhub_alias_exists():
    """_classify_instrument_via_finnhub alias still works for backward compat."""
    from app.services.sync import _classify_instrument_via_finnhub, _classify_instrument
    assert _classify_instrument_via_finnhub is _classify_instrument


# ── Curated ETF classification map ─────────────────────────────────────────

def test_curated_map_classifies_without_yfinance(db):
    """Symbol in curated JSON map gets all four fields without calling yfinance."""
    from app.services.sync import backfill_all_sectors

    db.add(Instrument(symbol="AIPI", name="Unknown ETF"))
    db.commit()

    with patch("app.services.yfinance_client.get_ticker_info") as mock_yf, \
         patch("app.services.finnhub.get_company_profile") as mock_fh, \
         patch("time.sleep"):
        count = backfill_all_sectors(db)

    # yfinance and Finnhub must NOT be called for a curated symbol
    mock_yf.assert_not_called()
    mock_fh.assert_not_called()

    assert count == 1
    inst = db.get(Instrument, "AIPI")
    assert inst.is_etf is True
    assert inst.asset_class == "Equity"
    assert inst.etf_category == "Thematic - AI / Covered Call"
    assert inst.sector == "Technology"
    assert inst.name == "REX AI Equity Premium Income ETF"


def test_curated_map_skips_already_populated(db):
    """Curated symbol with sector already set is skipped entirely."""
    from app.services.sync import backfill_all_sectors

    db.add(Instrument(symbol="SPYI", name="NEOS S&P 500", sector="Diversified"))
    db.commit()

    with patch("app.services.yfinance_client.get_ticker_info") as mock_yf, \
         patch("time.sleep"):
        count = backfill_all_sectors(db)

    mock_yf.assert_not_called()
    assert count == 0


def test_unknown_symbol_falls_through_to_yfinance(db):
    """Symbol NOT in curated map falls through to yfinance classification."""
    from app.services.sync import backfill_all_sectors

    db.add(Instrument(symbol="AAPL", name="Apple"))
    db.commit()

    with patch("app.services.yfinance_client.get_ticker_info", return_value=SAMPLE_YFINANCE_EQUITY), \
         patch("time.sleep"):
        count = backfill_all_sectors(db)

    assert count == 1
    inst = db.get(Instrument, "AAPL")
    assert inst.sector == "Technology"
    assert inst.is_etf is False
