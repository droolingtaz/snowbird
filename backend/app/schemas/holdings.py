from pydantic import BaseModel
from typing import Optional, List
from decimal import Decimal


class HoldingOut(BaseModel):
    model_config = {"from_attributes": True}

    symbol: str
    qty: float
    avg_entry_price: Optional[float] = None
    current_price: Optional[float] = None
    market_value: Optional[float] = None
    unrealized_pl: Optional[float] = None
    unrealized_plpc: Optional[float] = None
    weight_pct: float = 0.0
    sector: Optional[str] = None
    asset_class: Optional[str] = None
    name: Optional[str] = None
    bucket_names: List[str] = []
