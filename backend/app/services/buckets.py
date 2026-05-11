"""Bucket management: drift computation and rebalance algorithm."""
from __future__ import annotations

from decimal import Decimal
from typing import List, Optional
from collections import defaultdict

from sqlalchemy.orm import Session
from sqlalchemy import select

from app.models.bucket import Bucket, BucketHolding
from app.models.position import Position
from app.schemas.buckets import BucketDrift, DriftHolding, RebalanceOrder, RebalancePreview


def compute_drift(db: Session, account_id: int) -> List[BucketDrift]:
    buckets = db.execute(
        select(Bucket).where(Bucket.account_id == account_id)
    ).scalars().all()

    positions = db.execute(
        select(Position).where(Position.account_id == account_id)
    ).scalars().all()

    total_equity = sum(float(p.market_value or 0) for p in positions)
    mv_by_symbol = {p.symbol: float(p.market_value or 0) for p in positions}

    results = []
    for bucket in buckets:
        target_pct = float(bucket.target_weight_pct)
        target_value = total_equity * target_pct / 100.0

        # Actual value in this bucket
        actual_value = 0.0
        holding_drifts = []

        for h in bucket.holdings:
            mv = mv_by_symbol.get(h.symbol, 0.0)
            actual_value += mv

            effective_target_pct = target_pct * float(h.target_weight_within_bucket_pct) / 100.0
            actual_sym_pct = mv / total_equity * 100.0 if total_equity > 0 else 0.0
            drift = actual_sym_pct - effective_target_pct

            holding_drifts.append(DriftHolding(
                symbol=h.symbol,
                target_pct=round(effective_target_pct, 4),
                actual_pct=round(actual_sym_pct, 4),
                drift_pct=round(drift, 4),
                market_value=round(mv, 4),
            ))

        actual_pct = actual_value / total_equity * 100.0 if total_equity > 0 else 0.0
        drift_pct = actual_pct - target_pct

        results.append(BucketDrift(
            bucket_id=bucket.id,
            bucket_name=bucket.name,
            target_pct=round(target_pct, 4),
            actual_pct=round(actual_pct, 4),
            drift_pct=round(drift_pct, 4),
            holdings=holding_drifts,
        ))

    return results


def compute_rebalance(
    db: Session,
    account_id: int,
    cash_to_deploy: float,
    fractional: bool,
    account,  # AlpacaAccount for price lookup
    exclude_bucket_ids: Optional[set] = None,
) -> RebalancePreview:
    from app.services.market_data import get_quote_cached

    all_buckets = db.execute(
        select(Bucket).where(Bucket.account_id == account_id)
    ).scalars().all()

    buckets = [b for b in all_buckets if not exclude_bucket_ids or b.id not in exclude_bucket_ids]

    positions = db.execute(
        select(Position).where(Position.account_id == account_id)
    ).scalars().all()

    total_equity = sum(float(p.market_value or 0) for p in positions)
    mv_by_symbol = {p.symbol: float(p.market_value or 0) for p in positions}

    # Build effective targets by symbol (multiple buckets can hold same symbol)
    effective_targets: dict[str, float] = defaultdict(float)
    bucket_name_by_symbol: dict[str, str] = {}
    for bucket in buckets:
        for h in bucket.holdings:
            effective = float(bucket.target_weight_pct) * float(h.target_weight_within_bucket_pct) / 10000.0
            effective_targets[h.symbol] += effective
            bucket_name_by_symbol[h.symbol] = bucket.name

    orders = []
    total_buys = 0.0
    total_sells = 0.0

    # Fetch prices
    prices: dict[str, float] = {}
    for symbol in set(list(effective_targets.keys()) + list(mv_by_symbol.keys())):
        quote = get_quote_cached(account, symbol)
        if quote and quote.get("last_price"):
            prices[symbol] = float(quote["last_price"])
        elif symbol in mv_by_symbol:
            pos = next((p for p in positions if p.symbol == symbol), None)
            prices[symbol] = float(pos.current_price) if pos and pos.current_price else 0.0

    for symbol, target_pct in effective_targets.items():
        target_value = (total_equity + cash_to_deploy) * target_pct
        current_value = mv_by_symbol.get(symbol, 0.0)
        delta = target_value - current_value
        price = prices.get(symbol, 0.0)

        if abs(delta) < 1.0 or price <= 0:
            continue

        if cash_to_deploy > 0 and delta < 0:
            continue  # No sells when deploying cash

        side = "buy" if delta > 0 else "sell"
        qty = abs(delta) / price if price > 0 else 0
        if not fractional:
            qty = float(int(qty))  # Floor to whole shares
        if qty <= 0:
            continue

        notional = qty * price

        if side == "buy":
            total_buys += notional
        else:
            total_sells += notional

        orders.append(RebalanceOrder(
            symbol=symbol,
            side=side,
            qty=round(qty, 4),
            notional=round(notional, 2),
            est_price=round(price, 4),
            bucket_name=bucket_name_by_symbol.get(symbol),
        ))

    # Fetch cash available
    try:
        from app.services.alpaca import get_trading_client
        client = get_trading_client(account)
        acct = client.get_account()
        cash_available = float(acct.buying_power or 0)
    except Exception:
        cash_available = cash_to_deploy

    return RebalancePreview(
        orders=orders,
        total_buys=round(total_buys, 2),
        total_sells=round(total_sells, 2),
        cash_available=round(cash_available, 2),
    )
