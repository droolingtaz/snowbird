"""Finnhub earnings calendar integration with TTL cache."""
from __future__ import annotations

import logging
import time
from datetime import date
from typing import List

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

_FINNHUB_BASE = "https://finnhub.io/api/v1"
_CACHE: dict[tuple[str, str, str], tuple[float, list[dict]]] = {}
_CACHE_TTL = 6 * 3600  # 6 hours


def _cache_key(symbol: str, from_date: date, to_date: date) -> tuple[str, str, str]:
    return (symbol, str(from_date), str(to_date))


def get_earnings_calendar(symbol: str, from_date: date, to_date: date) -> List[dict]:
    """Fetch earnings calendar for a single symbol. Returns [] on error or missing key."""
    if not settings.FINNHUB_API_KEY:
        return []

    key = _cache_key(symbol, from_date, to_date)
    now = time.monotonic()
    if key in _CACHE:
        cached_at, data = _CACHE[key]
        if now - cached_at < _CACHE_TTL:
            return data

    url = f"{_FINNHUB_BASE}/calendar/earnings"
    params = {
        "symbol": symbol,
        "from": str(from_date),
        "to": str(to_date),
        "token": settings.FINNHUB_API_KEY,
    }
    delays = [1, 2, 4]
    for attempt, delay in enumerate(delays):
        try:
            resp = httpx.get(url, params=params, timeout=10.0)
            if resp.status_code == 429:
                logger.warning("Finnhub rate limit hit for %s, attempt %d", symbol, attempt + 1)
                time.sleep(delay)
                continue
            resp.raise_for_status()
            data = resp.json()
            earnings = data.get("earningsCalendar", [])
            _CACHE[key] = (now, earnings)
            return earnings
        except httpx.HTTPStatusError as exc:
            logger.warning("Finnhub HTTP error for %s: %s", symbol, exc)
            return []
        except Exception as exc:
            logger.warning("Finnhub request error for %s (attempt %d): %s", symbol, attempt + 1, exc)
            if attempt < len(delays) - 1:
                time.sleep(delay)
                continue
            return []
    return []


def get_earnings_for_symbols(symbols: list[str], from_date: date, to_date: date) -> list[dict]:
    """Fetch earnings for multiple symbols, rate-limiting between calls."""
    all_earnings: list[dict] = []
    for symbol in symbols:
        earnings = get_earnings_calendar(symbol, from_date, to_date)
        all_earnings.extend(earnings)
        if settings.FINNHUB_API_KEY:
            time.sleep(0.1)
    return all_earnings


def clear_cache() -> None:
    """Clear the in-memory earnings cache."""
    _CACHE.clear()
