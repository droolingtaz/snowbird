from datetime import date, datetime, timezone
from typing import Optional
from decimal import Decimal
from sqlalchemy import String, DateTime, Date, Numeric, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class Activity(Base):
    __tablename__ = "activities"

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("alpaca_accounts.id", ondelete="CASCADE"), nullable=False, index=True)
    alpaca_id: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    activity_type: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    symbol: Mapped[Optional[str]] = mapped_column(String(20), nullable=True, index=True)
    qty: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 4), nullable=True)
    price: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 4), nullable=True)
    net_amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 4), nullable=True)
    date: Mapped[Optional[date]] = mapped_column(Date, nullable=True, index=True)
    raw: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    account: Mapped["AlpacaAccount"] = relationship("AlpacaAccount", back_populates="activities")  # type: ignore[name-defined]
