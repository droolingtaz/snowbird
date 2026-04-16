"""Trading service: place and cancel orders via Alpaca."""
from __future__ import annotations

import logging
from typing import Optional
from sqlalchemy.orm import Session

from app.models.order import Order
from app.schemas.orders import OrderCreate
from app.services.alpaca import get_trading_client
from app.services.sync import _safe_decimal

logger = logging.getLogger(__name__)


def place_order(db: Session, account, order_in: OrderCreate) -> Order:
    from alpaca.trading.requests import (
        MarketOrderRequest, LimitOrderRequest, StopOrderRequest,
        StopLimitOrderRequest, TrailingStopOrderRequest,
        TakeProfitRequest, StopLossRequest,
    )
    from alpaca.trading.enums import OrderSide, TimeInForce, OrderClass

    client = get_trading_client(account)

    side = OrderSide.BUY if order_in.side.lower() == "buy" else OrderSide.SELL
    tif_map = {
        "day": TimeInForce.DAY,
        "gtc": TimeInForce.GTC,
        "ioc": TimeInForce.IOC,
        "fok": TimeInForce.FOK,
        "opg": TimeInForce.OPG,
        "cls": TimeInForce.CLS,
    }
    tif = tif_map.get(order_in.time_in_force.lower(), TimeInForce.DAY)

    order_class = OrderClass.BRACKET if order_in.bracket else OrderClass.SIMPLE
    take_profit = None
    stop_loss = None
    if order_in.bracket:
        if order_in.bracket.take_profit:
            take_profit = TakeProfitRequest(limit_price=order_in.bracket.take_profit)
        if order_in.bracket.stop_loss:
            stop_loss = StopLossRequest(stop_price=order_in.bracket.stop_loss)

    common = dict(
        symbol=order_in.symbol,
        side=side,
        time_in_force=tif,
    )
    if order_in.qty:
        common["qty"] = order_in.qty
    elif order_in.notional:
        common["notional"] = order_in.notional

    order_type = order_in.type.lower()
    if order_type == "market":
        req = MarketOrderRequest(**common)
    elif order_type == "limit":
        req = LimitOrderRequest(limit_price=order_in.limit_price, **common)
    elif order_type == "stop":
        req = StopOrderRequest(stop_price=order_in.stop_price, **common)
    elif order_type == "stop_limit":
        req = StopLimitOrderRequest(
            limit_price=order_in.limit_price,
            stop_price=order_in.stop_price,
            **common,
        )
    else:
        req = MarketOrderRequest(**common)

    if order_class == OrderClass.BRACKET and (take_profit or stop_loss):
        req.order_class = OrderClass.BRACKET
        if take_profit:
            req.take_profit = take_profit
        if stop_loss:
            req.stop_loss = stop_loss

    alpaca_order = client.submit_order(req)

    db_order = Order(
        account_id=account.id,
        alpaca_id=str(alpaca_order.id),
        client_order_id=str(alpaca_order.client_order_id) if alpaca_order.client_order_id else None,
        symbol=order_in.symbol,
        side=order_in.side.lower(),
        type=order_in.type.lower(),
        qty=_safe_decimal(order_in.qty),
        notional=_safe_decimal(order_in.notional),
        limit_price=_safe_decimal(order_in.limit_price),
        stop_price=_safe_decimal(order_in.stop_price),
        time_in_force=order_in.time_in_force,
        status=str(alpaca_order.status.value) if alpaca_order.status else "pending_new",
        raw={"id": str(alpaca_order.id)},
    )
    db.add(db_order)
    db.commit()
    db.refresh(db_order)
    return db_order


def cancel_order(db: Session, account, order_id: int) -> bool:
    """Cancel order by local ID."""
    from sqlalchemy import select
    db_order = db.execute(
        select(Order).where(Order.id == order_id, Order.account_id == account.id)
    ).scalar_one_or_none()

    if not db_order:
        return False

    if db_order.alpaca_id:
        try:
            client = get_trading_client(account)
            client.cancel_order_by_id(db_order.alpaca_id)
        except Exception as exc:
            logger.warning("Cancel order %s failed: %s", db_order.alpaca_id, exc)

    db_order.status = "canceled"
    db.commit()
    return True


def cancel_all_orders(db: Session, account) -> int:
    """Cancel all open orders."""
    try:
        client = get_trading_client(account)
        cancel_statuses = client.cancel_orders()
        count = len(cancel_statuses) if cancel_statuses else 0
    except Exception as exc:
        logger.warning("Cancel all failed: %s", exc)
        count = 0

    # Mark all open orders as canceled
    from sqlalchemy import update
    db.execute(
        Order.__table__.update()
        .where(Order.account_id == account.id, Order.status.in_(["new", "pending_new", "accepted", "held", "partially_filled"]))
        .values(status="canceled")
    )
    db.commit()
    return count
