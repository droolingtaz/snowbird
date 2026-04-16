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
