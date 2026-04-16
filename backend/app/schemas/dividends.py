from pydantic import BaseModel
from typing import Optional, List
from datetime import date


class DividendHistoryItem(BaseModel):
    symbol: str
    date: date
    net_amount: float
    qty: Optional[float] = None
    price: Optional[float] = None


class DividendCalendarItem(BaseModel):
    symbol: str
    ex_date: Optional[str] = None
    pay_date: Optional[str] = None
    amount_per_share: Optional[float] = None
    projected_income: Optional[float] = None


class DividendForecastMonth(BaseModel):
    month: str  # YYYY-MM
    projected_income: float
    symbols: List[str]


class DividendForecast(BaseModel):
    monthly: List[DividendForecastMonth]
    annual_total: float
    yield_on_cost: Optional[float] = None
    forward_yield: Optional[float] = None


class DividendBySymbol(BaseModel):
    symbol: str
    total_received: float
    ytd_received: float
    annual_dps: Optional[float] = None
    frequency: Optional[str] = None
    projected_annual: Optional[float] = None
    current_qty: float
