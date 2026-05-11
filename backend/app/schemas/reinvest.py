"""Pydantic schemas for dividend reinvestment."""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel


# ── Settings ──────────────────────────────────────────────────────────────────

class ReinvestSettingsOut(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    account_id: int
    tax_rate_pct: float
    tax_reserve_symbol: str
    auto_reinvest_enabled: bool
    auto_reinvest_threshold: float


class ReinvestSettingsUpdate(BaseModel):
    account_id: int
    tax_rate_pct: Optional[float] = None
    tax_reserve_symbol: Optional[str] = None
    auto_reinvest_enabled: Optional[bool] = None
    auto_reinvest_threshold: Optional[float] = None


# ── Preview / Plan ────────────────────────────────────────────────────────────

class ReinvestOrder(BaseModel):
    symbol: str
    side: str
    notional: float
    bucket_name: Optional[str] = None
    purpose: str  # "tax_reserve" | "investment"


class ReinvestPreview(BaseModel):
    unreinvested_cash: float
    tax_reserved: float
    investable: float
    cshi_order: Optional[ReinvestOrder] = None
    investment_orders: List[ReinvestOrder]
    total_orders: List[ReinvestOrder]


# ── Execute ───────────────────────────────────────────────────────────────────

class ReinvestExecuteRequest(BaseModel):
    account_id: int
    dry_run: bool = False


class ReinvestRunOut(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    account_id: int
    run_at: datetime
    trigger: str
    dividend_cash_total: float
    tax_reserved: float
    invested: float
    status: str
    orders_json: Optional[dict] = None
    error: Optional[str] = None
