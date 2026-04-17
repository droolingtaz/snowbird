"""Yahoo Finance integration for ETF/equity classification with Redis caching.

Includes aggressive throttling and exponential backoff to avoid 429 rate limits
from Yahoo Finance when running from data-center IPs.
"""
from __future__ import annotations

import json
import logging
import os
import random
import time
from typing import Any, Optional

logger = logging.getLogger(__name__)

_CACHE_TTL = 86400  # 24 hours

# Throttle: sleep between consecutive yfinance API calls (seconds).
YFINANCE_PER_CALL_SLEEP = float(os.environ.get("YFINANCE_PER_CALL_SLEEP_SECONDS", "7"))

# Retry / backoff settings for 429 and transient errors.
YFINANCE_MAX_RETRIES = int(os.environ.get("YFINANCE_MAX_RETRIES", "5"))
YFINANCE_BACKOFF_BASE = float(os.environ.get("YFINANCE_BACKOFF_BASE_SECONDS", "30"))
YFINANCE_BACKOFF_MULTIPLIER = float(os.environ.get("YFINANCE_BACKOFF_MULTIPLIER", "2"))
YFINANCE_BACKOFF_MAX = float(os.environ.get("YFINANCE_BACKOFF_MAX_SECONDS", "600"))
YFINANCE_JITTER_MAX = float(os.environ.get("YFINANCE_JITTER_MAX_SECONDS", "5"))


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


def _is_retryable(exc: Exception) -> bool:
    """Return True if the exception looks like a transient/rate-limit error."""
    msg = str(exc).lower()

    # Check for HTTP 429 (Too Many Requests)
    if "429" in msg or "too many requests" in msg or "rate limit" in msg:
        return True

    # Network / timeout errors
    if any(kw in msg for kw in (
        "timeout", "timed out", "connection", "connectionerror",
        "urlerror", "urlopen", "remotedisconnected", "brokenpipeerror",
        "ssl", "eof",
    )):
        return True

    # requests / urllib3 exceptions by type name
    exc_type = type(exc).__name__.lower()
    if any(kw in exc_type for kw in (
        "timeout", "connection", "retry", "httperror", "urlerror",
    )):
        return True

    return False


def _fetch_ticker_info(symbol: str) -> dict | None:
    """Raw yfinance call — no caching, no retries. Used internally."""
    import yfinance as yf

    ticker = yf.Ticker(symbol)
    info = ticker.info
    if not info or info.get("quoteType") is None:
        logger.warning("yfinance returned empty info for %s", symbol)
        return None

    return {
        "quoteType": info.get("quoteType"),
        "category": info.get("category"),
        "fundFamily": info.get("fundFamily"),
        "longName": info.get("longName"),
        "sector": info.get("sector") or info.get("sectorDisp"),
        "industry": info.get("industry") or info.get("industryDisp"),
    }


def get_ticker_info(
    symbol: str,
    *,
    _sleep_fn=time.sleep,
    _fetch_fn: Any = None,
) -> dict | None:
    """Fetch ticker info from Yahoo Finance via yfinance.

    Returns a dict with relevant keys (quoteType, category, sector, etc.)
    or None on failure.  Results are cached in Redis for 24 hours.

    Includes:
    - Per-call throttle sleep (``YFINANCE_PER_CALL_SLEEP_SECONDS`` env var, default 7s)
    - Exponential backoff with jitter on 429 / transient errors (up to 5 retries)
    """
    cache_key = f"yfinance:{symbol}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    fetch = _fetch_fn or _fetch_ticker_info

    # Throttle: wait before making the API call
    if YFINANCE_PER_CALL_SLEEP > 0:
        _sleep_fn(YFINANCE_PER_CALL_SLEEP)

    last_exc: Exception | None = None
    for attempt in range(1, YFINANCE_MAX_RETRIES + 1):
        try:
            result = fetch(symbol)
            if result is not None:
                _cache_set(cache_key, result)
            return result
        except Exception as exc:
            last_exc = exc
            if not _is_retryable(exc) or attempt == YFINANCE_MAX_RETRIES:
                logger.warning(
                    "yfinance lookup failed for %s (attempt %d/%d, non-retryable or final): %s",
                    symbol, attempt, YFINANCE_MAX_RETRIES, exc,
                )
                return None

            delay = min(
                YFINANCE_BACKOFF_BASE * (YFINANCE_BACKOFF_MULTIPLIER ** (attempt - 1)),
                YFINANCE_BACKOFF_MAX,
            )
            jitter = random.uniform(0, YFINANCE_JITTER_MAX)
            total_delay = delay + jitter
            logger.warning(
                "yfinance lookup for %s failed (attempt %d/%d): %s — retrying in %.1fs",
                symbol, attempt, YFINANCE_MAX_RETRIES, exc, total_delay,
            )
            _sleep_fn(total_delay)

    # Should not reach here, but just in case
    logger.warning("yfinance lookup exhausted retries for %s: %s", symbol, last_exc)
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
