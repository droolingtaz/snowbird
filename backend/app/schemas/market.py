from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


class AssetSearchResult(BaseModel):
    symbol: str
    name: Optional[str] = None
    asset_class: Optional[str] = None
    exchange: Optional[str] = None
    tradable: bool = True


class QuoteOut(BaseModel):
    symbol: str
    bid_price: Optional[float] = None
    ask_price: Optional[float] = None
    last_price: Optional[float] = None
    bid_size: Optional[float] = None
    ask_size: Optional[float] = None
    timestamp: Optional[datetime] = None


class BarOut(BaseModel):
    timestamp: str
    open: float
    high: float
    low: float
    close: float
    volume: float


class BarsResponse(BaseModel):
    symbol: str
    bars: List[BarOut]


class MarketClock(BaseModel):
    is_open: bool
    next_open: Optional[str] = None
    next_close: Optional[str] = None
    timestamp: Optional[str] = None
