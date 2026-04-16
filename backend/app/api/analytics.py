from fastapi import APIRouter, Query
from typing import List

from app.deps import CurrentUser, DbSession
from app.schemas.analytics import PerformanceMetrics, BenchmarkResponse, MonthlyReturn
from app.services.analytics import compute_performance, compute_benchmark, compute_monthly_returns

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/performance", response_model=PerformanceMetrics)
def performance(
    account_id: int,
    period: str = Query("1Y"),
    current_user: CurrentUser = None,
    db: DbSession = None,
):
    return compute_performance(db, account_id, period)


@router.get("/benchmark", response_model=BenchmarkResponse)
def benchmark(
    account_id: int,
    symbol: str = Query("SPY"),
    period: str = Query("1Y"),
    current_user: CurrentUser = None,
    db: DbSession = None,
):
    from sqlalchemy import select
    from app.models.account import AlpacaAccount
    acct = db.execute(
        select(AlpacaAccount).where(
            AlpacaAccount.id == account_id,
            AlpacaAccount.user_id == current_user.id,
        )
    ).scalar_one_or_none()

    points, port_ret, bench_ret = compute_benchmark(db, account_id, symbol, period)
    return BenchmarkResponse(
        symbol=symbol,
        points=points,
        portfolio_return=port_ret,
        benchmark_return=bench_ret,
    )


@router.get("/monthly", response_model=List[MonthlyReturn])
def monthly_returns(
    account_id: int,
    current_user: CurrentUser = None,
    db: DbSession = None,
):
    return compute_monthly_returns(db, account_id)
