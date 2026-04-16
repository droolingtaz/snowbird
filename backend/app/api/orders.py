from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select
from typing import List, Optional

from app.deps import CurrentUser, DbSession
from app.models.order import Order
from app.models.account import AlpacaAccount
from app.schemas.orders import OrderCreate, OrderOut
from app.services.trading import place_order, cancel_order, cancel_all_orders

router = APIRouter(prefix="/orders", tags=["orders"])


def _get_account_or_404(db, user_id: int, account_id: int) -> AlpacaAccount:
    acct = db.execute(
        select(AlpacaAccount).where(
            AlpacaAccount.id == account_id,
            AlpacaAccount.user_id == user_id,
        )
    ).scalar_one_or_none()
    if not acct:
        raise HTTPException(status_code=404, detail="Account not found")
    return acct


@router.get("", response_model=List[OrderOut])
def list_orders(
    account_id: int,
    status: str = Query("all"),
    current_user: CurrentUser = None,
    db: DbSession = None,
):
    _get_account_or_404(db, current_user.id, account_id)
    query = select(Order).where(Order.account_id == account_id)
    if status == "open":
        query = query.where(Order.status.in_(["new", "pending_new", "accepted", "held", "partially_filled"]))
    elif status == "closed":
        query = query.where(Order.status.in_(["filled", "canceled", "expired", "replaced"]))
    query = query.order_by(Order.submitted_at.desc().nullslast(), Order.id.desc())
    orders = db.execute(query).scalars().all()
    return orders


@router.post("", response_model=OrderOut, status_code=201)
def create_order(body: OrderCreate, current_user: CurrentUser, db: DbSession):
    acct = _get_account_or_404(db, current_user.id, body.account_id)
    try:
        order = place_order(db, acct, body)
        return order
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.delete("/{order_id}", status_code=204)
def cancel_single_order(
    order_id: int,
    account_id: int,
    current_user: CurrentUser,
    db: DbSession,
):
    acct = _get_account_or_404(db, current_user.id, account_id)
    success = cancel_order(db, acct, order_id)
    if not success:
        raise HTTPException(status_code=404, detail="Order not found")


@router.delete("", status_code=200)
def cancel_all(account_id: int, current_user: CurrentUser, db: DbSession):
    acct = _get_account_or_404(db, current_user.id, account_id)
    count = cancel_all_orders(db, acct)
    return {"canceled": count}
