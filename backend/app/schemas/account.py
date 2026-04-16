from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional
from app.models.account import AccountMode


class AccountCreate(BaseModel):
    label: str = Field(max_length=100)
    mode: AccountMode = AccountMode.paper
    api_key: str
    api_secret: str


class AccountUpdate(BaseModel):
    label: Optional[str] = None
    api_key: Optional[str] = None
    api_secret: Optional[str] = None
    active: Optional[bool] = None


class AccountOut(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    label: str
    mode: AccountMode
    api_key: str
    base_url: str
    active: bool
    last_sync_at: Optional[datetime] = None
    created_at: datetime


class AccountTestResult(BaseModel):
    ok: bool
    message: str
    account_id: Optional[str] = None
    buying_power: Optional[float] = None
