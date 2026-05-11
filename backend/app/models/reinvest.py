"""Dividend reinvestment settings and run audit trail."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import String, DateTime, Numeric, Boolean, ForeignKey, JSON, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class DividendReinvestSettings(Base):
    __tablename__ = "dividend_reinvest_settings"

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("alpaca_accounts.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    tax_rate_pct: Mapped[Decimal] = mapped_column(
        Numeric(9, 4), nullable=False, default=Decimal("24.0000"),
    )
    tax_reserve_symbol: Mapped[str] = mapped_column(
        String(20), nullable=False, default="CSHI",
    )
    auto_reinvest_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False,
    )
    auto_reinvest_threshold: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("50.0000"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    account: Mapped["AlpacaAccount"] = relationship("AlpacaAccount")  # type: ignore[name-defined]


class DividendReinvestRun(Base):
    __tablename__ = "dividend_reinvest_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("alpaca_accounts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    run_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    trigger: Mapped[str] = mapped_column(String(20), nullable=False)
    dividend_cash_total: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    tax_reserved: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    invested: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    orders_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    account: Mapped["AlpacaAccount"] = relationship("AlpacaAccount")  # type: ignore[name-defined]
