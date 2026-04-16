from pydantic import BaseModel
from typing import Optional, List
from decimal import Decimal
from datetime import date


class PortfolioSummary(BaseModel):
    equity: float
    cash: float
    buying_power: float
    today_pl: float
    today_pl_pct: float
    total_pl: float
    positions_count: int


class HistoryPoint(BaseModel):
    date: str
    equity: float
    pnl: float


class PortfolioHistory(BaseModel):
    points: List[HistoryPoint]
    base_value: float


class AllocationItem(BaseModel):
    label: str
    value: float
    pct: float


class AllocationResponse(BaseModel):
    items: List[AllocationItem]
    total: float
