"""Market data: bars, quotes, search — with Redis caching."""
from __future__ import annotations

import json
import logging
from datetime import date, timedelta
from typing import List, Optional, Any

from sqlalchemy.orm import Session
from sqlalchemy import select

logger = logging.getLogger(__name__)

_redis_client: Any = None


def _get_redis():
    global _redis_client
    if _redis_client is None:
        try:
            import redis as redis_lib
            from app.config import settings
            _redis_client = redis_lib.from_url(settings.REDIS_URL, decode_responses=True)
        except Exception as exc:
            logger.warning("Redis unavailable: %s", exc)
            _redis_client = None
    return _redis_client


def _cache_get(key: str) -> Optional[Any]:
    r = _get_redis()
    if not r:
        return None
    try:
        val = r.get(key)
        return json.loads(val) if val else None
    except Exception:
        return None


def _cache_set(key: str, value: Any, ttl: int = 60) -> None:
    r = _get_redis()
    if not r:
        return
    try:
        r.setex(key, ttl, json.dumps(value))
    except Exception:
        pass


def get_quote_cached(account, symbol: str) -> Optional[dict]:
    """Fetch latest quote with Redis cache (60s TTL)."""
    cache_key = f"quote:{symbol}"
    cached = _cache_get(cache_key)
    if cached:
        return cached

    try:
        from app.services.alpaca import get_data_client
        from alpaca.data.requests import StockLatestQuoteRequest
        client = get_data_client(account)
        req = StockLatestQuoteRequest(symbol_or_symbols=[symbol])
        resp = client.get_stock_latest_quote(req)
        quote = resp.get(symbol)
        if quote:
            result = {
                "symbol": symbol,
                "bid_price": float(quote.bid_price) if quote.bid_price else None,
                "ask_price": float(quote.ask_price) if quote.ask_price else None,
                "last_price": float((quote.ask_price + quote.bid_price) / 2) if quote.ask_price and quote.bid_price else None,
                "bid_size": float(quote.bid_size) if quote.bid_size else None,
                "ask_size": float(quote.ask_size) if quote.ask_size else None,
                "timestamp": str(quote.timestamp) if quote.timestamp else None,
            }
            _cache_set(cache_key, result, ttl=60)
            return result
    except Exception as exc:
        logger.warning("Quote fetch failed for %s: %s", symbol, exc)

    return None


def get_bars_cached(symbol: str, timeframe: str, start: str, end: str, account=None) -> List[dict]:
    """Fetch historical bars with caching."""
    cache_key = f"bars:{symbol}:{timeframe}:{start}:{end}"
    cached = _cache_get(cache_key)
    if cached:
        return cached

    if account is None:
        return []

    try:
        from app.services.alpaca import get_data_client
        from alpaca.data.requests import StockBarsRequest
        from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
        from alpaca.data.enums import DataFeed
        from datetime import datetime

        timeframe_map = {
            "1Min": TimeFrame.Minute,
            "5Min": TimeFrame(5, TimeFrameUnit.Minute),
            "15Min": TimeFrame(15, TimeFrameUnit.Minute),
            "1Hour": TimeFrame.Hour,
            "1Day": TimeFrame.Day,
            "1Week": TimeFrame.Week,
            "1Month": TimeFrame.Month,
        }
        tf = timeframe_map.get(timeframe, TimeFrame.Day)

        client = get_data_client(account)
        req = StockBarsRequest(
            symbol_or_symbols=[symbol],
            timeframe=tf,
            start=datetime.fromisoformat(start) if "T" not in start else datetime.fromisoformat(start),
            end=datetime.fromisoformat(end) if "T" not in end else datetime.fromisoformat(end),
            feed=DataFeed.IEX,
        )
        resp = client.get_stock_bars(req)
        bars_data = resp.data.get(symbol, [])
        result = [
            {
                "timestamp": str(b.timestamp),
                "open": float(b.open),
                "high": float(b.high),
                "low": float(b.low),
                "close": float(b.close),
                "volume": float(b.volume),
            }
            for b in bars_data
        ]
        ttl = 300 if timeframe in ("1Day", "1Week", "1Month") else 60
        _cache_set(cache_key, result, ttl=ttl)
        return result
    except Exception as exc:
        logger.warning("Bars fetch failed for %s: %s", symbol, exc)
        return []


def search_assets(account, query: str) -> List[dict]:
    """Search assets by symbol or name."""
    cache_key = f"search:{query.upper()}"
    cached = _cache_get(cache_key)
    if cached:
        return cached

    try:
        from app.services.alpaca import get_trading_client
        from alpaca.trading.requests import GetAssetsRequest
        from alpaca.trading.enums import AssetClass, AssetStatus

        client = get_trading_client(account)
        # Alpaca doesn't support free-text search; filter by name pattern
        req = GetAssetsRequest(asset_class=AssetClass.US_EQUITY, status=AssetStatus.ACTIVE)
        assets = client.get_all_assets(req)

        q = query.upper()
        results = []
        for a in assets:
            sym = str(a.symbol).upper()
            name = str(a.name).upper() if a.name else ""
            if q in sym or q in name:
                results.append({
                    "symbol": str(a.symbol),
                    "name": str(a.name) if a.name else None,
                    "asset_class": str(a.asset_class.value) if a.asset_class else None,
                    "exchange": str(a.exchange.value) if a.exchange else None,
                    "tradable": bool(a.tradable),
                })
                if len(results) >= 20:
                    break

        _cache_set(cache_key, results, ttl=300)
        return results
    except Exception as exc:
        logger.warning("Asset search failed: %s", exc)
        return []


def get_market_clock(account) -> dict:
    """Get current market clock."""
    try:
        from app.services.alpaca import get_trading_client
        client = get_trading_client(account)
        clock = client.get_clock()
        return {
            "is_open": bool(clock.is_open),
            "next_open": str(clock.next_open) if clock.next_open else None,
            "next_close": str(clock.next_close) if clock.next_close else None,
            "timestamp": str(clock.timestamp) if clock.timestamp else None,
        }
    except Exception as exc:
        logger.warning("Market clock failed: %s", exc)
        return {"is_open": False, "next_open": None, "next_close": None, "timestamp": None}
