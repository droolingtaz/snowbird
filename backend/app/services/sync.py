"""Sync engine: pulls data from Alpaca into the local DB."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, date, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy import select

from alpaca.trading.client import TradingClient
from alpaca.trading.requests import GetOrdersRequest, GetPortfolioHistoryRequest
from alpaca.trading.enums import QueryOrderStatus

from app.models.account import AlpacaAccount
from app.models.position import Position
from app.models.order import Order
from app.models.activity import Activity
from app.models.snapshot import PortfolioSnapshot
from app.models.instrument import Instrument
from app.services.alpaca import get_trading_client, get_data_client

logger = logging.getLogger(__name__)


def _safe_decimal(val) -> Optional[Decimal]:
    if val is None:
        return None
    try:
        return Decimal(str(val))
    except Exception:
        return None


def sync_account(db: Session, account: AlpacaAccount) -> None:
    """Full sync: positions, orders, activities, snapshot."""
    try:
        client = get_trading_client(account)
        _sync_positions(db, client, account)
        _sync_orders(db, client, account)
        _sync_activities(db, client, account, days=7)
        _snapshot_equity(db, client, account)
        account.last_sync_at = datetime.now(timezone.utc)
        db.commit()
    except Exception as exc:
        logger.error("Sync error for account %s: %s", account.id, exc)
        db.rollback()


def _sync_positions(db: Session, client: TradingClient, account: AlpacaAccount) -> None:
    positions = client.get_all_positions()
    seen_symbols = set()
    for pos in positions:
        symbol = str(pos.symbol)
        seen_symbols.add(symbol)
        existing = db.execute(
            select(Position).where(
                Position.account_id == account.id,
                Position.symbol == symbol,
            )
        ).scalar_one_or_none()

        if existing:
            existing.qty = _safe_decimal(pos.qty) or Decimal("0")
            existing.avg_entry_price = _safe_decimal(pos.avg_entry_price)
            existing.market_value = _safe_decimal(pos.market_value)
            existing.unrealized_pl = _safe_decimal(pos.unrealized_pl)
            existing.unrealized_plpc = _safe_decimal(pos.unrealized_plpc)
            existing.current_price = _safe_decimal(pos.current_price)
            existing.updated_at = datetime.now(timezone.utc)
        else:
            new_pos = Position(
                account_id=account.id,
                symbol=symbol,
                qty=_safe_decimal(pos.qty) or Decimal("0"),
                avg_entry_price=_safe_decimal(pos.avg_entry_price),
                market_value=_safe_decimal(pos.market_value),
                unrealized_pl=_safe_decimal(pos.unrealized_pl),
                unrealized_plpc=_safe_decimal(pos.unrealized_plpc),
                current_price=_safe_decimal(pos.current_price),
            )
            db.add(new_pos)

    # Remove positions no longer held
    db.execute(
        Position.__table__.delete().where(
            Position.account_id == account.id,
            Position.symbol.notin_(seen_symbols),
        )
    )
    db.flush()


def _sync_orders(db: Session, client: TradingClient, account: AlpacaAccount) -> None:
    req = GetOrdersRequest(status=QueryOrderStatus.ALL, limit=200)
    orders = client.get_orders(filter=req)
    for o in orders:
        alpaca_id = str(o.id)
        existing = db.execute(
            select(Order).where(Order.alpaca_id == alpaca_id)
        ).scalar_one_or_none()

        raw = {
            "id": alpaca_id,
            "status": str(o.status),
            "symbol": str(o.symbol),
        }

        if existing:
            existing.status = str(o.status)
            existing.filled_qty = _safe_decimal(o.filled_qty)
            existing.filled_avg_price = _safe_decimal(o.filled_avg_price)
            existing.filled_at = o.filled_at
            existing.raw = raw
        else:
            new_order = Order(
                account_id=account.id,
                alpaca_id=alpaca_id,
                client_order_id=str(o.client_order_id) if o.client_order_id else None,
                symbol=str(o.symbol),
                side=str(o.side.value) if o.side else "buy",
                type=str(o.type.value) if o.type else "market",
                qty=_safe_decimal(o.qty),
                notional=_safe_decimal(o.notional),
                limit_price=_safe_decimal(o.limit_price),
                stop_price=_safe_decimal(o.stop_price),
                time_in_force=str(o.time_in_force.value) if o.time_in_force else "day",
                status=str(o.status.value) if o.status else None,
                filled_qty=_safe_decimal(o.filled_qty),
                filled_avg_price=_safe_decimal(o.filled_avg_price),
                submitted_at=o.submitted_at,
                filled_at=o.filled_at,
                raw=raw,
            )
            db.add(new_order)
    db.flush()


def _sync_activities(db: Session, client: TradingClient, account: AlpacaAccount, days: int = 7) -> None:
    try:
        from alpaca.trading.requests import GetAccountActivitiesRequest
        since = datetime.now(timezone.utc) - timedelta(days=days)
        req = GetAccountActivitiesRequest(after=since)
        activities = client.get_account_activities(activity_filter=req)
    except Exception as exc:
        logger.warning("Could not fetch activities (skipping): %s", exc)
        return

    for act in activities:
        alpaca_id = str(act.id)
        existing = db.execute(
            select(Activity).where(Activity.alpaca_id == alpaca_id)
        ).scalar_one_or_none()
        if existing:
            continue

        activity_date = None
        if hasattr(act, "date") and act.date:
            if isinstance(act.date, date):
                activity_date = act.date
            else:
                try:
                    activity_date = datetime.fromisoformat(str(act.date)).date()
                except Exception:
                    pass
        elif hasattr(act, "transaction_time") and act.transaction_time:
            activity_date = act.transaction_time.date()

        new_act = Activity(
            account_id=account.id,
            alpaca_id=alpaca_id,
            activity_type=str(act.activity_type.value) if hasattr(act.activity_type, "value") else str(act.activity_type),
            symbol=str(act.symbol) if hasattr(act, "symbol") and act.symbol else None,
            qty=_safe_decimal(act.qty) if hasattr(act, "qty") else None,
            price=_safe_decimal(act.price) if hasattr(act, "price") else None,
            net_amount=_safe_decimal(act.net_amount) if hasattr(act, "net_amount") else None,
            date=activity_date,
            raw={"id": alpaca_id, "type": str(act.activity_type)},
        )
        db.add(new_act)
    db.flush()


def _snapshot_equity(db: Session, client: TradingClient, account: AlpacaAccount) -> None:
    """Save today's equity snapshot."""
    try:
        alpaca_acct = client.get_account()
        today = date.today()
        equity = _safe_decimal(alpaca_acct.equity) or Decimal("0")
        cash = _safe_decimal(alpaca_acct.cash) or Decimal("0")
        long_mv = _safe_decimal(alpaca_acct.long_market_value) or Decimal("0")

        existing = db.execute(
            select(PortfolioSnapshot).where(
                PortfolioSnapshot.account_id == account.id,
                PortfolioSnapshot.date == today,
            )
        ).scalar_one_or_none()

        if existing:
            existing.equity = equity
            existing.cash = cash
            existing.long_market_value = long_mv
        else:
            snap = PortfolioSnapshot(
                account_id=account.id,
                date=today,
                equity=equity,
                cash=cash,
                long_market_value=long_mv,
            )
            db.add(snap)
        db.flush()
    except Exception as exc:
        logger.error("Snapshot error: %s", exc)


def refresh_instruments(db: Session, account: AlpacaAccount) -> None:
    """Refresh instrument metadata for held symbols."""
    from alpaca.trading.requests import GetAssetsRequest
    client = get_trading_client(account)
    positions = db.execute(
        select(Position).where(Position.account_id == account.id)
    ).scalars().all()

    for pos in positions:
        try:
            asset = client.get_asset(pos.symbol)
            existing = db.get(Instrument, pos.symbol)
            if existing:
                existing.name = str(asset.name) if asset.name else None
                existing.asset_class = str(asset.asset_class.value) if asset.asset_class else None
                existing.exchange = str(asset.exchange.value) if asset.exchange else None
                existing.updated_at = datetime.now(timezone.utc)
            else:
                inst = Instrument(
                    symbol=pos.symbol,
                    name=str(asset.name) if asset.name else None,
                    asset_class=str(asset.asset_class.value) if asset.asset_class else None,
                    exchange=str(asset.exchange.value) if asset.exchange else None,
                    currency="USD",
                )
                db.add(inst)
        except Exception as exc:
            logger.warning("Failed to refresh instrument %s: %s", pos.symbol, exc)

    db.commit()
