from fastapi import APIRouter
from sqlalchemy import select
from typing import List

from app.deps import CurrentUser, DbSession
from app.models.position import Position
from app.models.instrument import Instrument
from app.models.bucket import Bucket, BucketHolding
from app.schemas.holdings import HoldingOut

router = APIRouter(prefix="/holdings", tags=["holdings"])


@router.get("", response_model=List[HoldingOut])
def list_holdings(account_id: int, current_user: CurrentUser, db: DbSession):
    positions = db.execute(
        select(Position).where(Position.account_id == account_id)
    ).scalars().all()

    total_mv = sum(float(p.market_value or 0) for p in positions)

    # Build bucket map: symbol -> list of bucket names
    buckets = db.execute(select(Bucket).where(Bucket.account_id == account_id)).scalars().all()
    symbol_buckets: dict[str, list] = {}
    for b in buckets:
        for h in b.holdings:
            symbol_buckets.setdefault(h.symbol, []).append(b.name)

    results = []
    for pos in positions:
        inst = db.get(Instrument, pos.symbol)
        mv = float(pos.market_value or 0)
        weight = mv / total_mv * 100 if total_mv > 0 else 0.0

        results.append(HoldingOut(
            symbol=pos.symbol,
            qty=float(pos.qty),
            avg_entry_price=float(pos.avg_entry_price) if pos.avg_entry_price else None,
            current_price=float(pos.current_price) if pos.current_price else None,
            market_value=float(pos.market_value) if pos.market_value else None,
            unrealized_pl=float(pos.unrealized_pl) if pos.unrealized_pl else None,
            unrealized_plpc=float(pos.unrealized_plpc) if pos.unrealized_plpc else None,
            weight_pct=round(weight, 4),
            sector=inst.sector if inst else None,
            asset_class=inst.asset_class if inst else None,
            name=inst.name if inst else None,
            dividend_tax_type=inst.dividend_tax_type if inst else None,
            dividend_tax_notes=inst.dividend_tax_notes if inst else None,
            bucket_names=symbol_buckets.get(pos.symbol, []),
        ))

    return sorted(results, key=lambda x: -(x.market_value or 0))
