from pydantic import BaseModel
from typing import Optional, List


class PerformanceMetrics(BaseModel):
    twr: Optional[float] = None
    cagr: Optional[float] = None
    total_return_pct: Optional[float] = None
    volatility: Optional[float] = None
    sharpe: Optional[float] = None
    max_drawdown: Optional[float] = None
    best_day: Optional[float] = None
    worst_day: Optional[float] = None
    days: int = 0


class BenchmarkPoint(BaseModel):
    date: str
    portfolio: float
    benchmark: float


class BenchmarkResponse(BaseModel):
    symbol: str
    points: List[BenchmarkPoint]
    portfolio_return: Optional[float] = None
    benchmark_return: Optional[float] = None


class MonthlyReturn(BaseModel):
    year: int
    month: int
    return_pct: Optional[float] = None


class IrrResponse(BaseModel):
    period: str
    irr: Optional[float] = None
    as_of: str


class PassiveIncomeResponse(BaseModel):
    annual_income: float = 0.0
    monthly_income: float = 0.0
    current_yield_pct: Optional[float] = None
    yoy_growth_pct: Optional[float] = None


class MoverItem(BaseModel):
    symbol: str
    name: Optional[str] = None
    value: Optional[float] = None
    change_pct: Optional[float] = None
    change_usd: Optional[float] = None


class MoversResponse(BaseModel):
    gainers: List[MoverItem] = []
    losers: List[MoverItem] = []
