from pydantic import BaseModel
from typing import Optional, List


class GoalUpsert(BaseModel):
    target_annual_income: float
    assumed_annual_growth_pct: float = 8.0
    assumed_monthly_contribution: float = 0.0


class GoalResponse(BaseModel):
    id: int
    target_annual_income: float
    assumed_annual_growth_pct: float
    assumed_monthly_contribution: float


class ProjectionYear(BaseModel):
    year: int
    equity: float
    projected_income: float


class GoalProjectionResponse(BaseModel):
    goal: GoalResponse
    current_equity: float
    current_annual_income: float
    current_yield_pct: Optional[float] = None
    projection: List[ProjectionYear] = []
    eta_year: Optional[int] = None
    years_to_goal: Optional[int] = None
