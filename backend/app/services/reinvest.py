"""Dividend reinvestment: tax reserve + bucket-target distribution."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Optional

from sqlalchemy import select, and_
from sqlalchemy.orm import Session

from app.models.activity import Activity
from app.models.bucket import Bucket, BucketHolding
from app.models.reinvest import DividendReinvestRun, DividendReinvestSettings
from app.schemas.orders import OrderCreate
from app.schemas.reinvest import ReinvestOrder, ReinvestPreview

logger = logging.getLogger(__name__)

DIV_TYPES = ["DIV", "DIVCGL", "DIVCGS", "DIVNRA", "DIVROC", "DIVTXEX"]


# ── Settings helpers ──────────────────────────────────────────────────────────

def get_or_create_settings(db: Session, account_id: int) -> DividendReinvestSettings:
    settings = db.execute(
        select(DividendReinvestSettings).where(
            DividendReinvestSettings.account_id == account_id,
        )
    ).scalar_one_or_none()

    if settings is None:
        settings = DividendReinvestSettings(account_id=account_id)
        db.add(settings)
        db.commit()
        db.refresh(settings)

    return settings


# ── Unreinvested dividend cash ────────────────────────────────────────────────

def get_unreinvested_dividend_cash(db: Session, account_id: int) -> Decimal:
    last_executed = db.execute(
        select(DividendReinvestRun)
        .where(
            DividendReinvestRun.account_id == account_id,
            DividendReinvestRun.status == "executed",
        )
        .order_by(DividendReinvestRun.run_at.desc())
        .limit(1)
    ).scalar_one_or_none()

    query = select(Activity).where(
        Activity.account_id == account_id,
        Activity.activity_type.in_(DIV_TYPES),
    )

    if last_executed is not None:
        query = query.where(Activity.created_at > last_executed.run_at)

    activities = db.execute(query).scalars().all()
    total = sum((a.net_amount or Decimal(0)) for a in activities)
    return total


# ── Tax Reserve bucket ────────────────────────────────────────────────────────

TAX_RESERVE_BUCKET_NAME = "Tax Reserve"


def ensure_tax_reserve_bucket(
    db: Session, account_id: int, symbol: str = "CSHI", *, user_id: int,
) -> Bucket:
    bucket = db.execute(
        select(Bucket).where(
            Bucket.user_id == user_id,
            Bucket.account_id == account_id,
            Bucket.name == TAX_RESERVE_BUCKET_NAME,
        )
    ).scalar_one_or_none()

    if bucket is None:
        bucket = Bucket(
            user_id=user_id,
            account_id=account_id,
            name=TAX_RESERVE_BUCKET_NAME,
            target_weight_pct=Decimal(0),
        )
        db.add(bucket)
        db.flush()

    # Ensure the holding exists
    holding = db.execute(
        select(BucketHolding).where(
            BucketHolding.bucket_id == bucket.id,
            BucketHolding.symbol == symbol,
        )
    ).scalar_one_or_none()

    if holding is None:
        holding = BucketHolding(
            bucket_id=bucket.id,
            user_id=user_id,
            account_id=account_id,
            symbol=symbol,
            target_weight_within_bucket_pct=Decimal(100),
        )
        db.add(holding)

    db.commit()
    db.refresh(bucket)
    return bucket


# ── Compute reinvestment plan ─────────────────────────────────────────────────

def compute_reinvest_plan(
    db: Session,
    account_id: int,
    dividend_cash: Decimal,
    settings: DividendReinvestSettings,
    account,  # AlpacaAccount for price lookup
) -> ReinvestPreview:
    from app.services.buckets import compute_rebalance

    tax_rate = settings.tax_rate_pct
    tax_reserved = (dividend_cash * tax_rate / Decimal(100)).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP,
    )
    investable = dividend_cash - tax_reserved
    tax_symbol = settings.tax_reserve_symbol

    # CSHI order for tax reserve
    cshi_order: Optional[ReinvestOrder] = None
    if tax_reserved > 0:
        cshi_order = ReinvestOrder(
            symbol=tax_symbol,
            side="buy",
            notional=float(tax_reserved),
            bucket_name=TAX_RESERVE_BUCKET_NAME,
            purpose="tax_reserve",
        )

    # Investment orders via existing bucket-target rebalance
    investment_orders: List[ReinvestOrder] = []
    if investable > 0:
        # Find the tax reserve bucket to exclude
        tax_bucket = db.execute(
            select(Bucket).where(
                Bucket.account_id == account_id,
                Bucket.name == TAX_RESERVE_BUCKET_NAME,
            )
        ).scalar_one_or_none()
        exclude_ids = {tax_bucket.id} if tax_bucket else set()

        preview = compute_rebalance(
            db,
            account_id,
            cash_to_deploy=float(investable),
            fractional=True,
            account=account,
            exclude_bucket_ids=exclude_ids,
        )

        for order in preview.orders:
            if order.side == "buy":
                investment_orders.append(ReinvestOrder(
                    symbol=order.symbol,
                    side="buy",
                    notional=order.notional,
                    bucket_name=order.bucket_name,
                    purpose="investment",
                ))

    total_orders: List[ReinvestOrder] = []
    if cshi_order:
        total_orders.append(cshi_order)
    total_orders.extend(investment_orders)

    return ReinvestPreview(
        unreinvested_cash=float(dividend_cash),
        tax_reserved=float(tax_reserved),
        investable=float(investable),
        cshi_order=cshi_order,
        investment_orders=investment_orders,
        total_orders=total_orders,
    )


# ── Execute reinvestment plan ─────────────────────────────────────────────────

def execute_reinvest_plan(
    db: Session,
    account,  # AlpacaAccount
    plan: ReinvestPreview,
    trigger: str = "manual",
) -> DividendReinvestRun:
    from app.services.trading import place_order

    run = DividendReinvestRun(
        account_id=account.id,
        run_at=datetime.now(timezone.utc),
        trigger=trigger,
        dividend_cash_total=Decimal(str(plan.unreinvested_cash)),
        tax_reserved=Decimal(str(plan.tax_reserved)),
        invested=Decimal(str(plan.investable)),
        status="preview",
    )
    db.add(run)
    db.flush()

    placed = []
    errors = []

    for order in plan.total_orders:
        try:
            order_in = OrderCreate(
                account_id=account.id,
                symbol=order.symbol,
                side="buy",
                type="market",
                notional=order.notional,
                time_in_force="day",
            )
            db_order = place_order(db, account, order_in)
            placed.append({
                "symbol": order.symbol,
                "order_id": db_order.id,
                "alpaca_id": db_order.alpaca_id,
                "notional": order.notional,
                "purpose": order.purpose,
            })
        except Exception as exc:
            logger.error("Reinvest order failed for %s: %s", order.symbol, exc)
            errors.append({
                "symbol": order.symbol,
                "notional": order.notional,
                "purpose": order.purpose,
                "error": str(exc),
            })

    if errors:
        run.status = "failed"
        run.error = "; ".join(e["error"] for e in errors)
    else:
        run.status = "executed"

    run.orders_json = {"placed": placed, "errors": errors}
    db.commit()
    db.refresh(run)
    return run
