"""Income goal CRUD and projection computation."""
from __future__ import annotations

from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session
from sqlalchemy import select

from app.models.user_goal import UserGoal
from app.models.position import Position
from app.models.instrument import Instrument
from app.models.activity import Activity
from app.schemas.goals import GoalResponse, GoalProjectionResponse, ProjectionYear


DIV_TYPES = ["DIV", "DIVCGL", "DIVCGS", "DIVNRA", "DIVROC", "DIVTXEX"]


def get_goal(db: Session, user_id: int) -> Optional[GoalResponse]:
    """Return the user's income goal, or None."""
    goal = db.execute(
        select(UserGoal).where(UserGoal.user_id == user_id)
    ).scalar_one_or_none()
    if not goal:
        return None
    return GoalResponse(
        id=goal.id,
        target_annual_income=float(goal.target_annual_income),
        assumed_annual_growth_pct=float(goal.assumed_annual_growth_pct),
        assumed_monthly_contribution=float(goal.assumed_monthly_contribution),
    )


def upsert_goal(
    db: Session,
    user_id: int,
    target_annual_income: float,
    assumed_annual_growth_pct: float = 8.0,
    assumed_monthly_contribution: float = 0.0,
) -> GoalResponse:
    """Create or update the user's income goal."""
    goal = db.execute(
        select(UserGoal).where(UserGoal.user_id == user_id)
    ).scalar_one_or_none()

    if goal:
        goal.target_annual_income = Decimal(str(target_annual_income))
        goal.assumed_annual_growth_pct = Decimal(str(assumed_annual_growth_pct))
        goal.assumed_monthly_contribution = Decimal(str(assumed_monthly_contribution))
    else:
        goal = UserGoal(
            user_id=user_id,
            target_annual_income=Decimal(str(target_annual_income)),
            assumed_annual_growth_pct=Decimal(str(assumed_annual_growth_pct)),
            assumed_monthly_contribution=Decimal(str(assumed_monthly_contribution)),
        )
        db.add(goal)

    db.commit()
    db.refresh(goal)
    return GoalResponse(
        id=goal.id,
        target_annual_income=float(goal.target_annual_income),
        assumed_annual_growth_pct=float(goal.assumed_annual_growth_pct),
        assumed_monthly_contribution=float(goal.assumed_monthly_contribution),
    )


def compute_projection(
    db: Session, user_id: int, account_id: int
) -> Optional[GoalProjectionResponse]:
    """Project forward until income target is reached (max 30 years)."""
    goal = db.execute(
        select(UserGoal).where(UserGoal.user_id == user_id)
    ).scalar_one_or_none()
    if not goal:
        return None

    positions = db.execute(
        select(Position).where(Position.account_id == account_id)
    ).scalars().all()
    current_equity = sum(float(p.market_value or 0) for p in positions)

    from datetime import date, timedelta
    today = date.today()
    one_year_ago = today - timedelta(days=365)
    divs = db.execute(
        select(Activity).where(
            Activity.account_id == account_id,
            Activity.activity_type.in_(DIV_TYPES),
            Activity.date >= one_year_ago,
        )
    ).scalars().all()
    current_annual_income = sum(float(a.net_amount or 0) for a in divs)

    yield_pct = (current_annual_income / current_equity * 100) if current_equity > 0 else None
    yield_rate = current_annual_income / current_equity if current_equity > 0 else 0.02

    growth_rate = float(goal.assumed_annual_growth_pct) / 100.0
    monthly_contrib = float(goal.assumed_monthly_contribution)
    target = float(goal.target_annual_income)

    equity = current_equity
    projection = []
    eta_year = None
    current_year = today.year

    for i in range(31):
        income = equity * yield_rate
        projection.append(ProjectionYear(
            year=current_year + i,
            equity=round(equity, 2),
            projected_income=round(income, 2),
        ))
        if income >= target and eta_year is None:
            eta_year = current_year + i
        equity = equity * (1 + growth_rate) + monthly_contrib * 12

    goal_resp = GoalResponse(
        id=goal.id,
        target_annual_income=float(goal.target_annual_income),
        assumed_annual_growth_pct=float(goal.assumed_annual_growth_pct),
        assumed_monthly_contribution=float(goal.assumed_monthly_contribution),
    )

    return GoalProjectionResponse(
        goal=goal_resp,
        current_equity=round(current_equity, 2),
        current_annual_income=round(current_annual_income, 2),
        current_yield_pct=round(yield_pct, 2) if yield_pct is not None else None,
        projection=projection,
        eta_year=eta_year,
        years_to_goal=(eta_year - current_year) if eta_year else None,
    )
