from fastapi import APIRouter, Query, HTTPException

from app.deps import CurrentUser, DbSession
from app.schemas.goals import GoalUpsert, GoalResponse, GoalProjectionResponse
from app.services.goals import get_goal, upsert_goal, compute_projection

router = APIRouter(prefix="/goals", tags=["goals"])


@router.get("", response_model=GoalResponse)
def read_goal(
    current_user: CurrentUser = None,
    db: DbSession = None,
):
    goal = get_goal(db, current_user.id)
    if not goal:
        raise HTTPException(status_code=404, detail="No income goal set")
    return goal


@router.put("", response_model=GoalResponse)
def set_goal(
    body: GoalUpsert,
    current_user: CurrentUser = None,
    db: DbSession = None,
):
    return upsert_goal(
        db,
        current_user.id,
        target_annual_income=body.target_annual_income,
        assumed_annual_growth_pct=body.assumed_annual_growth_pct,
        assumed_monthly_contribution=body.assumed_monthly_contribution,
    )


@router.get("/projection", response_model=GoalProjectionResponse)
def goal_projection(
    account_id: int,
    current_user: CurrentUser = None,
    db: DbSession = None,
):
    result = compute_projection(db, current_user.id, account_id)
    if not result:
        raise HTTPException(status_code=404, detail="No income goal set")
    return result
