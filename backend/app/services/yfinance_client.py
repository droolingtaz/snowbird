"""Yahoo Finance integration for ETF/equity classification with Redis caching."""
from __future__ import annotations

import json
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

_CACHE_TTL = 86400  # 24 hours


def _get_redis():
    """Reuse the Redis connection pattern from market_data."""
    try:
        import redis as redis_lib
        from app.config import settings

        return redis_lib.from_url(settings.REDIS_URL, decode_responses=True)
    except Exception:
        return None


def _cache_get(key: str) -> Optional[Any]:
    r = _get_redis()
    if not r:
        return None
    try:
        val = r.get(key)
        return json.loads(val) if val else None
    except Exception:
        return None


def _cache_set(key: str, value: Any, ttl: int = _CACHE_TTL) -> None:
    r = _get_redis()
    if not r:
        return
    try:
        r.setex(key, ttl, json.dumps(value))
    except Exception:
        pass


def get_ticker_info(symbol: str) -> dict | None:
    """Fetch ticker info from Yahoo Finance via yfinance.

    Returns a dict with relevant keys (quoteType, category, sector, etc.)
    or None on failure.  Results are cached in Redis for 24 hours.
    """
    cache_key = f"yfinance:{symbol}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    try:
        import yfinance as yf

        ticker = yf.Ticker(symbol)
        info = ticker.info
        if not info or info.get("quoteType") is None:
            logger.warning("yfinance returned empty info for %s", symbol)
            return None

        result = {
            "quoteType": info.get("quoteType"),
            "category": info.get("category"),
            "fundFamily": info.get("fundFamily"),
            "longName": info.get("longName"),
            "sector": info.get("sector") or info.get("sectorDisp"),
            "industry": info.get("industry") or info.get("industryDisp"),
        }

        _cache_set(cache_key, result)
        return result
    except Exception as exc:
        logger.warning("yfinance lookup failed for %s: %s", symbol, exc)
        return None


def derive_asset_class(quote_type: str | None, category: str | None) -> str:
    """Derive asset class from yfinance quoteType and category.

    Returns one of: Fixed Income, Commodities, Crypto, Real Estate, Equity, Other.
    """
    if not quote_type:
        return "Other"

    qt = quote_type.upper()

    if qt == "ETF" and category:
        cat = category.lower()
        if any(kw in cat for kw in ("treasury", "bond", "credit", "government", "fixed income")):
            return "Fixed Income"
        if any(kw in cat for kw in ("gold", "silver", "commodit", "natural resource")):
            return "Commodities"
        if any(kw in cat for kw in ("crypto", "digital")):
            return "Crypto"
        if any(kw in cat for kw in ("real estate", "reit")):
            return "Real Estate"
        return "Equity"

    if qt == "EQUITY":
        return "Equity"

    return "Other"
