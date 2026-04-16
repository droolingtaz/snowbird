from pydantic import BaseModel
from typing import Optional, List
from decimal import Decimal
from datetime import datetime


class BracketParams(BaseModel):
    take_profit: Optional[float] = None
    stop_loss: Optional[float] = None


class OrderCreate(BaseModel):
    account_id: int
    symbol: str
    side: str  # buy | sell
    type: str  # market | limit | stop | stop_limit
    qty: Optional[float] = None
    notional: Optional[float] = None
    time_in_force: str = "day"
    limit_price: Optional[float] = None
    stop_price: Optional[float] = None
    bracket: Optional[BracketParams] = None


class OrderOut(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    alpaca_id: Optional[str] = None
    symbol: str
    side: str
    type: str
    qty: Optional[float] = None
    notional: Optional[float] = None
    limit_price: Optional[float] = None
    stop_price: Optional[float] = None
    time_in_force: Optional[str] = None
    status: Optional[str] = None
    filled_qty: Optional[float] = None
    filled_avg_price: Optional[float] = None
    submitted_at: Optional[datetime] = None
    filled_at: Optional[datetime] = None
