from pydantic import BaseModel, field_validator
from typing import Optional, List


class BucketHoldingCreate(BaseModel):
    symbol: str
    target_weight_within_bucket_pct: float


class BucketCreate(BaseModel):
    account_id: Optional[int] = None
    name: str
    target_weight_pct: float
    color: Optional[str] = None
    notes: Optional[str] = None
    holdings: List[BucketHoldingCreate] = []


class BucketUpdate(BaseModel):
    name: Optional[str] = None
    target_weight_pct: Optional[float] = None
    color: Optional[str] = None
    notes: Optional[str] = None
    holdings: Optional[List[BucketHoldingCreate]] = None


class BucketLink(BaseModel):
    account_id: Optional[int] = None


class BucketHoldingOut(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    symbol: str
    target_weight_within_bucket_pct: float


class BucketOut(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    user_id: int
    account_id: Optional[int] = None
    linked: bool = False
    name: str
    target_weight_pct: float
    color: Optional[str] = None
    notes: Optional[str] = None
    holdings: List[BucketHoldingOut] = []
    actual_weight_pct: Optional[float] = None
    drift_pct: Optional[float] = None


class DriftHolding(BaseModel):
    symbol: str
    target_pct: float
    actual_pct: float
    drift_pct: float
    market_value: float


class BucketDrift(BaseModel):
    bucket_id: int
    bucket_name: str
    target_pct: float
    actual_pct: float
    drift_pct: float
    holdings: List[DriftHolding]


class RebalanceOrder(BaseModel):
    symbol: str
    side: str
    qty: Optional[float] = None
    notional: float
    est_price: Optional[float] = None
    bucket_name: Optional[str] = None


class RebalancePreview(BaseModel):
    orders: List[RebalanceOrder]
    total_buys: float
    total_sells: float
    cash_available: float


class RebalanceExecuteRequest(BaseModel):
    account_id: int
    orders: List[RebalanceOrder]
    dry_run: bool = True


class RebalanceExecuteResult(BaseModel):
    placed: List[dict]
    errors: List[dict]
    dry_run: bool
