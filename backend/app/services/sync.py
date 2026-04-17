"""Sync engine: pulls data from Alpaca into the local DB."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, date, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session
from sqlalchemy import select, func

from alpaca.trading.client import TradingClient
from alpaca.trading.requests import GetOrdersRequest
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
    account_id = account.id
    try:
        client = get_trading_client(account)
        if account.last_sync_at is None:
            _backfill_snapshots(db, client, account)
        _sync_positions(db, client, account)
        _sync_orders(db, client, account)
        _sync_activities(db, client, account)
        _snapshot_equity(db, client, account)
        account.last_sync_at = datetime.now(timezone.utc)
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.error("Sync error for account %s: %s", account_id, exc)


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


_MIN_LOOKBACK_DAYS = 7
_MAX_LOOKBACK_DAYS = 90


def _sync_activities(db: Session, client: TradingClient, account: AlpacaAccount) -> None:
    """Fetch activities via raw REST (alpaca-py 0.26.0 lacks get_account_activities).

    Lookback window is computed dynamically from the most recent activity
    already stored for this account (gap + 2-day margin, clamped to 7–90 days).
    First sync for an account defaults to the full 90-day window.
    """
    try:
        import httpx
        from app.security import decrypt_secret

        latest = db.execute(
            select(func.max(Activity.date)).where(
                Activity.account_id == account.id
            )
        ).scalar()

        if latest is None:
            lookback_days = _MAX_LOOKBACK_DAYS
        else:
            gap = (datetime.now(timezone.utc).date() - latest).days + 2
            lookback_days = max(_MIN_LOOKBACK_DAYS, min(gap, _MAX_LOOKBACK_DAYS))

        since = datetime.now(timezone.utc) - timedelta(days=lookback_days)
        logger.info(
            "Activity sync for account %s: lookback=%d days",
            account.id, lookback_days,
        )
        api_secret = decrypt_secret(account.api_secret_enc)

        resp = httpx.get(
            f"{account.base_url}/v2/account/activities",
            headers={
                "APCA-API-KEY-ID": account.api_key,
                "APCA-API-SECRET-KEY": api_secret,
            },
            params={
                "after": since.strftime("%Y-%m-%dT%H:%M:%SZ"),
            },
            timeout=30.0,
        )
        resp.raise_for_status()
        activities = resp.json()
    except Exception as exc:
        logger.warning("Could not fetch activities (skipping): %s", exc)
        return

    for act in activities:
        alpaca_id = str(act.get("id", ""))
        if not alpaca_id:
            continue

        existing = db.execute(
            select(Activity).where(Activity.alpaca_id == alpaca_id)
        ).scalar_one_or_none()
        if existing:
            continue

        activity_date = None
        raw_date = act.get("date") or act.get("transaction_time")
        if raw_date:
            try:
                activity_date = datetime.fromisoformat(str(raw_date).replace("Z", "+00:00")).date()
            except Exception:
                pass

        new_act = Activity(
            account_id=account.id,
            alpaca_id=alpaca_id,
            activity_type=str(act.get("activity_type", "")),
            symbol=act.get("symbol"),
            qty=_safe_decimal(act.get("qty")),
            price=_safe_decimal(act.get("price")),
            net_amount=_safe_decimal(act.get("net_amount")),
            date=activity_date,
            raw=act,
        )
        db.add(new_act)
    db.flush()


def _backfill_snapshots(db: Session, client: TradingClient, account: AlpacaAccount) -> None:
    """Backfill daily portfolio snapshots from Alpaca's portfolio history endpoint.

    Called once per account (when last_sync_at is None) to populate historical
    equity data so the Performance tab can compute returns.
    """
    try:
        import httpx
        from app.security import decrypt_secret

        api_secret = decrypt_secret(account.api_secret_enc)
        resp = httpx.get(
            f"{account.base_url}/v2/account/portfolio/history",
            headers={
                "APCA-API-KEY-ID": account.api_key,
                "APCA-API-SECRET-KEY": api_secret,
            },
            params={"period": "1A", "timeframe": "1D"},
            timeout=30.0,
        )
        resp.raise_for_status()
        history = resp.json()

        timestamps = history.get("timestamp", [])
        equities = history.get("equity", [])
        profit_losses = history.get("profit_loss", [])

        # Build payload rows, skipping null equity days
        payload = []
        for i, ts in enumerate(timestamps):
            snap_date = datetime.fromtimestamp(ts, tz=timezone.utc).date()
            equity_val = _safe_decimal(equities[i]) if i < len(equities) and equities[i] is not None else None
            if equity_val is None:
                continue
            pnl = _safe_decimal(profit_losses[i]) if i < len(profit_losses) and profit_losses[i] is not None else None
            payload.append({"account_id": account.id, "date": snap_date, "equity": equity_val, "pnl": pnl})

        if payload:
            # Use dialect-appropriate INSERT ... ON CONFLICT DO NOTHING
            dialect_name = db.bind.dialect.name if db.bind else "postgresql"
            if dialect_name == "sqlite":
                from sqlalchemy.dialects.sqlite import insert as dialect_insert
            else:
                from sqlalchemy.dialects.postgresql import insert as dialect_insert
            stmt = dialect_insert(PortfolioSnapshot.__table__).values(payload)
            stmt = stmt.on_conflict_do_nothing(index_elements=["account_id", "date"])
            db.execute(stmt)
            db.flush()

        logger.info("Backfilled portfolio snapshots for account %s", account.id)
    except Exception as exc:
        logger.warning("Could not backfill portfolio snapshots (skipping): %s", exc)


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

    # Backfill sector/industry from Finnhub company profiles
    _backfill_sectors(db, [p.symbol for p in positions])


def _classify_instrument_via_finnhub(
    inst: Instrument,
    *,
    _time_module: object | None = None,
) -> bool:
    """Try stock profile first; fall back to ETF endpoints if empty.

    Updates ``inst`` in place and returns ``True`` if any field was changed.
    Callers are responsible for committing the session.
    """
    import time as _default_time
    from app.services.finnhub import (
        get_company_profile,
        get_etf_profile,
        get_etf_sector_exposure,
    )

    _time = _time_module or _default_time
    changed = False

    # --- 1. Try stock profile ---
    profile = get_company_profile(inst.symbol)
    _time.sleep(1.1)  # rate-limit

    if profile:
        sector = profile.get("finnhubIndustry")
        if sector:
            inst.sector = sector
            inst.is_etf = False
            inst.updated_at = datetime.now(timezone.utc)
            changed = True
            logger.info("Updated stock sector for %s -> %s", inst.symbol, sector)
        return changed

    # --- 2. Stock profile empty → try ETF profile ---
    etf_profile = get_etf_profile(inst.symbol)
    _time.sleep(1.1)

    if etf_profile:
        inst.is_etf = True
        category = etf_profile.get("category")
        if category:
            inst.etf_category = category
        asset_cls = etf_profile.get("assetClass")
        if asset_cls:
            inst.asset_class = asset_cls
        inst.updated_at = datetime.now(timezone.utc)
        changed = True
        logger.info(
            "Updated ETF profile for %s -> category=%s, asset_class=%s",
            inst.symbol, category, asset_cls,
        )

    # --- 3. ETF sector exposure → derive dominant GICS sector ---
    sectors = get_etf_sector_exposure(inst.symbol)
    _time.sleep(1.1)

    if sectors:
        # Pick the sector with the highest exposure weight
        top = max(sectors, key=lambda s: s.get("exposure", 0))
        inst.sector = top.get("industry", "Diversified")
        inst.updated_at = datetime.now(timezone.utc)
        changed = True
        logger.info(
            "Updated ETF sector for %s -> %s (%.1f%%)",
            inst.symbol, inst.sector, top.get("exposure", 0),
        )
    elif etf_profile and not inst.sector:
        inst.sector = "Diversified"
        inst.updated_at = datetime.now(timezone.utc)
        changed = True

    return changed


def _backfill_sectors(db: Session, symbols: list[str]) -> None:
    """Classify instruments via Finnhub (stock profile first, then ETF endpoints)."""
    unique_symbols = sorted(set(symbols))
    updated = 0
    for sym in unique_symbols:
        inst = db.get(Instrument, sym)
        if inst is None:
            continue
        # Skip if sector already populated (avoids unnecessary API calls)
        if inst.sector:
            logger.debug("Sector already set for %s, skipping Finnhub call", sym)
            continue
        if _classify_instrument_via_finnhub(inst):
            updated += 1

    if updated:
        db.commit()
        logger.info("Backfilled sector for %d instruments", updated)


def backfill_all_sectors(db: Session) -> int:
    """Backfill sectors for every instrument row — used by CLI / admin tasks.

    Uses stock profile first, then falls back to ETF endpoints.
    Returns the number of instruments updated.
    """
    instruments = db.execute(select(Instrument)).scalars().all()
    updated = 0
    total = len(instruments)
    for idx, inst in enumerate(instruments, 1):
        if inst.sector:
            logger.debug("[%d/%d] %s already has sector=%s", idx, total, inst.symbol, inst.sector)
            continue
        if _classify_instrument_via_finnhub(inst):
            updated += 1
            logger.info("[%d/%d] %s -> sector=%s, etf=%s", idx, total, inst.symbol, inst.sector, inst.is_etf)
        else:
            logger.info("[%d/%d] No Finnhub data for %s", idx, total, inst.symbol)

    if updated:
        db.commit()
    logger.info("Backfill complete: %d/%d instruments updated", updated, total)
    return updated
