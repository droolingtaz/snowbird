from fastapi import APIRouter, Query
from typing import List

from sqlalchemy import select

from app.deps import CurrentUser, DbSession
from app.models.account import AlpacaAccount
from app.schemas.analytics import (
    PerformanceMetrics, BenchmarkResponse, MonthlyReturn,
    IrrResponse, PassiveIncomeResponse, MoversResponse,
)
from app.services.analytics import (
    compute_performance, compute_benchmark, compute_monthly_returns,
    compute_irr, compute_passive_income, compute_movers,
)

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
    acct = db.execute(
        select(AlpacaAccount).where(
            AlpacaAccount.id == account_id,
            AlpacaAccount.user_id == current_user.id,
        )
    ).scalar_one_or_none()

    points, port_ret, bench_ret = compute_benchmark(db, account_id, symbol, period, account=acct)
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


@router.get("/irr", response_model=IrrResponse)
def irr(
    account_id: int,
    period: str = Query("1Y"),
    current_user: CurrentUser = None,
    db: DbSession = None,
):
    return compute_irr(db, account_id, period)


@router.get("/passive-income", response_model=PassiveIncomeResponse)
def passive_income(
    account_id: int,
    current_user: CurrentUser = None,
    db: DbSession = None,
):
    return compute_passive_income(db, account_id)


@router.get("/movers", response_model=MoversResponse)
def movers(
    account_id: int,
    limit: int = Query(5, ge=1, le=20),
    current_user: CurrentUser = None,
    db: DbSession = None,
):
    acct = db.execute(
        select(AlpacaAccount).where(
            AlpacaAccount.id == account_id,
            AlpacaAccount.user_id == current_user.id,
        )
    ).scalar_one_or_none()
    return compute_movers(db, account_id, acct, limit)
