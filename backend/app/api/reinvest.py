"""API endpoints for dividend reinvestment."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select
from typing import List

from app.deps import CurrentUser, DbSession
from app.models.account import AlpacaAccount
from app.models.reinvest import DividendReinvestRun
from app.schemas.reinvest import (
    ReinvestExecuteRequest,
    ReinvestPreview,
    ReinvestRunOut,
    ReinvestSettingsOut,
    ReinvestSettingsUpdate,
)
from app.services.reinvest import (
    compute_reinvest_plan,
    ensure_tax_reserve_bucket,
    execute_reinvest_plan,
    get_or_create_settings,
    get_unreinvested_dividend_cash,
)

router = APIRouter(prefix="/reinvest", tags=["reinvest"])


def _get_account(db, user_id: int, account_id: int) -> AlpacaAccount:
    acct = db.execute(
        select(AlpacaAccount).where(
            AlpacaAccount.id == account_id,
            AlpacaAccount.user_id == user_id,
        )
    ).scalar_one_or_none()
    if not acct:
        raise HTTPException(status_code=404, detail="Account not found")
    return acct


# ── Settings ──────────────────────────────────────────────────────────────────

@router.get("/settings", response_model=ReinvestSettingsOut)
def get_settings(account_id: int, current_user: CurrentUser, db: DbSession):
    _get_account(db, current_user.id, account_id)
    return get_or_create_settings(db, account_id)


@router.put("/settings", response_model=ReinvestSettingsOut)
def update_settings(body: ReinvestSettingsUpdate, current_user: CurrentUser, db: DbSession):
    _get_account(db, current_user.id, body.account_id)
    settings = get_or_create_settings(db, body.account_id)

    if body.tax_rate_pct is not None:
        settings.tax_rate_pct = body.tax_rate_pct
    if body.tax_reserve_symbol is not None:
        settings.tax_reserve_symbol = body.tax_reserve_symbol
    if body.auto_reinvest_enabled is not None:
        settings.auto_reinvest_enabled = body.auto_reinvest_enabled
    if body.auto_reinvest_threshold is not None:
        settings.auto_reinvest_threshold = body.auto_reinvest_threshold

    db.commit()
    db.refresh(settings)
    return settings


# ── Preview ───────────────────────────────────────────────────────────────────

@router.get("/preview", response_model=ReinvestPreview)
def preview(account_id: int, current_user: CurrentUser, db: DbSession):
    acct = _get_account(db, current_user.id, account_id)
    settings = get_or_create_settings(db, account_id)
    ensure_tax_reserve_bucket(db, account_id, symbol=settings.tax_reserve_symbol)
    dividend_cash = get_unreinvested_dividend_cash(db, account_id)
    return compute_reinvest_plan(db, account_id, dividend_cash, settings, acct)


# ── Execute ───────────────────────────────────────────────────────────────────

@router.post("/execute", response_model=ReinvestRunOut)
def execute(body: ReinvestExecuteRequest, current_user: CurrentUser, db: DbSession):
    acct = _get_account(db, current_user.id, body.account_id)
    settings = get_or_create_settings(db, body.account_id)
    ensure_tax_reserve_bucket(db, body.account_id, symbol=settings.tax_reserve_symbol)
    dividend_cash = get_unreinvested_dividend_cash(db, body.account_id)

    if dividend_cash <= 0:
        raise HTTPException(status_code=400, detail="No unreinvested dividend cash available")

    plan = compute_reinvest_plan(db, body.account_id, dividend_cash, settings, acct)

    if body.dry_run:
        run = DividendReinvestRun(
            account_id=body.account_id,
            trigger="manual",
            dividend_cash_total=dividend_cash,
            tax_reserved=plan.tax_reserved,
            invested=plan.investable,
            status="preview",
            orders_json={"total_orders": [o.model_dump() for o in plan.total_orders]},
        )
        db.add(run)
        db.commit()
        db.refresh(run)
        return run

    return execute_reinvest_plan(db, acct, plan, trigger="manual")


# ── History ───────────────────────────────────────────────────────────────────

@router.get("/history", response_model=List[ReinvestRunOut])
def history(
    account_id: int,
    current_user: CurrentUser,
    db: DbSession,
    limit: int = Query(default=20, le=100),
):
    _get_account(db, current_user.id, account_id)
    runs = db.execute(
        select(DividendReinvestRun)
        .where(DividendReinvestRun.account_id == account_id)
        .order_by(DividendReinvestRun.run_at.desc())
        .limit(limit)
    ).scalars().all()
    return runs
