from datetime import datetime, timezone
from typing import Optional
from decimal import Decimal
from sqlalchemy import Boolean, String, DateTime, Numeric
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Instrument(Base):
    __tablename__ = "instruments"

    symbol: Mapped[str] = mapped_column(String(20), primary_key=True)
    name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    asset_class: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    exchange: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    currency: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    sector: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    industry: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    is_etf: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True, default=False)
    etf_category: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    dividend_tax_type: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    dividend_tax_notes: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    dividend_yield: Mapped[Optional[Decimal]] = mapped_column(Numeric(9, 4), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
