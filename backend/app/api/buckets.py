from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select
from typing import List, Optional

from app.deps import CurrentUser, DbSession
from app.models.account import AlpacaAccount
from app.models.bucket import Bucket, BucketHolding
from app.schemas.buckets import (
    BucketCreate, BucketUpdate, BucketOut, BucketDrift, BucketLink,
    RebalancePreview, RebalanceExecuteRequest, RebalanceExecuteResult,
)
from app.services.buckets import compute_drift, compute_rebalance
from app.services.trading import place_order
from app.schemas.orders import OrderCreate

router = APIRouter(prefix="/buckets", tags=["buckets"])


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


def _get_user_bucket(db, user_id: int, bucket_id: int) -> Bucket:
    bucket = db.execute(
        select(Bucket).where(Bucket.id == bucket_id, Bucket.user_id == user_id)
    ).scalar_one_or_none()
    if not bucket:
        raise HTTPException(status_code=404, detail="Bucket not found")
    return bucket


@router.get("", response_model=List[BucketOut])
def list_buckets(
    current_user: CurrentUser,
    db: DbSession,
    account_id: Optional[int] = Query(default=None),
):
    query = select(Bucket).where(Bucket.user_id == current_user.id)
    if account_id is not None:
        _get_account(db, current_user.id, account_id)
        query = query.where(Bucket.account_id == account_id)

    buckets = db.execute(query).scalars().all()

    # Compute actual weights when an account is linked
    from app.models.position import Position

    results = []
    for b in buckets:
        actual_pct = 0.0
        drift = 0.0
        if b.account_id is not None:
            positions = db.execute(
                select(Position).where(Position.account_id == b.account_id)
            ).scalars().all()
            total_mv = sum(float(p.market_value or 0) for p in positions)
            mv_by_symbol = {p.symbol: float(p.market_value or 0) for p in positions}
            actual_value = sum(mv_by_symbol.get(h.symbol, 0.0) for h in b.holdings)
            actual_pct = actual_value / total_mv * 100 if total_mv > 0 else 0.0
            drift = actual_pct - float(b.target_weight_pct)

        out = BucketOut(
            id=b.id,
            user_id=b.user_id,
            account_id=b.account_id,
            linked=b.account_id is not None,
            name=b.name,
            target_weight_pct=float(b.target_weight_pct),
            color=b.color,
            notes=b.notes,
            holdings=[
                {"id": h.id, "symbol": h.symbol, "target_weight_within_bucket_pct": float(h.target_weight_within_bucket_pct)}
                for h in b.holdings
            ],
            actual_weight_pct=round(actual_pct, 4),
            drift_pct=round(drift, 4),
        )
        results.append(out)
    return results


@router.post("", response_model=BucketOut, status_code=201)
def create_bucket(body: BucketCreate, current_user: CurrentUser, db: DbSession):
    if body.account_id is not None:
        _get_account(db, current_user.id, body.account_id)

    bucket = Bucket(
        user_id=current_user.id,
        account_id=body.account_id,
        name=body.name,
        target_weight_pct=body.target_weight_pct,
        color=body.color,
        notes=body.notes,
    )
    db.add(bucket)
    db.flush()
    for h in body.holdings:
        holding = BucketHolding(
            bucket_id=bucket.id,
            user_id=current_user.id,
            account_id=body.account_id,
            symbol=h.symbol,
            target_weight_within_bucket_pct=h.target_weight_within_bucket_pct,
        )
        db.add(holding)
    db.commit()
    db.refresh(bucket)
    return BucketOut(
        id=bucket.id,
        user_id=bucket.user_id,
        account_id=bucket.account_id,
        linked=bucket.account_id is not None,
        name=bucket.name,
        target_weight_pct=float(bucket.target_weight_pct),
        color=bucket.color,
        notes=bucket.notes,
        holdings=[{"id": h.id, "symbol": h.symbol, "target_weight_within_bucket_pct": float(h.target_weight_within_bucket_pct)} for h in bucket.holdings],
    )


@router.put("/{bucket_id}", response_model=BucketOut)
def update_bucket(bucket_id: int, body: BucketUpdate, current_user: CurrentUser, db: DbSession):
    bucket = _get_user_bucket(db, current_user.id, bucket_id)

    if body.name is not None:
        bucket.name = body.name
    if body.target_weight_pct is not None:
        bucket.target_weight_pct = body.target_weight_pct
    if body.color is not None:
        bucket.color = body.color
    if body.notes is not None:
        bucket.notes = body.notes
    if body.holdings is not None:
        for h in bucket.holdings:
            db.delete(h)
        db.flush()
        for h in body.holdings:
            holding = BucketHolding(
                bucket_id=bucket.id,
                user_id=current_user.id,
                account_id=bucket.account_id,
                symbol=h.symbol,
                target_weight_within_bucket_pct=h.target_weight_within_bucket_pct,
            )
            db.add(holding)

    db.commit()
    db.refresh(bucket)
    return BucketOut(
        id=bucket.id,
        user_id=bucket.user_id,
        account_id=bucket.account_id,
        linked=bucket.account_id is not None,
        name=bucket.name,
        target_weight_pct=float(bucket.target_weight_pct),
        color=bucket.color,
        notes=bucket.notes,
        holdings=[{"id": h.id, "symbol": h.symbol, "target_weight_within_bucket_pct": float(h.target_weight_within_bucket_pct)} for h in bucket.holdings],
    )


@router.delete("/{bucket_id}", status_code=204)
def delete_bucket(bucket_id: int, current_user: CurrentUser, db: DbSession):
    bucket = _get_user_bucket(db, current_user.id, bucket_id)
    db.delete(bucket)
    db.commit()


@router.patch("/{bucket_id}/link", response_model=BucketOut)
def link_bucket(bucket_id: int, body: BucketLink, current_user: CurrentUser, db: DbSession):
    bucket = _get_user_bucket(db, current_user.id, bucket_id)

    if body.account_id is not None:
        _get_account(db, current_user.id, body.account_id)

    bucket.account_id = body.account_id
    for h in bucket.holdings:
        h.account_id = body.account_id
    db.commit()
    db.refresh(bucket)

    return BucketOut(
        id=bucket.id,
        user_id=bucket.user_id,
        account_id=bucket.account_id,
        linked=bucket.account_id is not None,
        name=bucket.name,
        target_weight_pct=float(bucket.target_weight_pct),
        color=bucket.color,
        notes=bucket.notes,
        holdings=[{"id": h.id, "symbol": h.symbol, "target_weight_within_bucket_pct": float(h.target_weight_within_bucket_pct)} for h in bucket.holdings],
    )


@router.get("/drift", response_model=List[BucketDrift])
def bucket_drift(account_id: int, current_user: CurrentUser, db: DbSession):
    _get_account(db, current_user.id, account_id)
    return compute_drift(db, account_id)


@router.get("/rebalance", response_model=RebalancePreview)
def rebalance_preview(
    account_id: int,
    cash_to_deploy: float = Query(default=0.0),
    current_user: CurrentUser = None,
    db: DbSession = None,
):
    acct = _get_account(db, current_user.id, account_id)
    return compute_rebalance(db, account_id, cash_to_deploy, fractional=True, account=acct)


@router.post("/rebalance/execute", response_model=RebalanceExecuteResult)
def rebalance_execute(body: RebalanceExecuteRequest, current_user: CurrentUser, db: DbSession):
    acct = _get_account(db, current_user.id, body.account_id)

    if body.dry_run:
        return RebalanceExecuteResult(placed=[], errors=[], dry_run=True)

    placed = []
    errors = []
    for order in body.orders:
        try:
            order_in = OrderCreate(
                account_id=body.account_id,
                symbol=order.symbol,
                side=order.side,
                type="market",
                qty=order.qty,
                time_in_force="day",
            )
            db_order = place_order(db, acct, order_in)
            placed.append({"symbol": order.symbol, "order_id": db_order.id, "alpaca_id": db_order.alpaca_id})
        except Exception as exc:
            errors.append({"symbol": order.symbol, "error": str(exc)})

    return RebalanceExecuteResult(placed=placed, errors=errors, dry_run=False)
