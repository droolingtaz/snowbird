from datetime import datetime, timezone
from typing import Optional
from decimal import Decimal
from sqlalchemy import String, DateTime, Numeric, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("alpaca_accounts.id", ondelete="CASCADE"), nullable=False, index=True)
    alpaca_id: Mapped[Optional[str]] = mapped_column(String(50), unique=True, nullable=True, index=True)
    client_order_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    side: Mapped[str] = mapped_column(String(10), nullable=False)
    type: Mapped[str] = mapped_column(String(20), nullable=False)
    qty: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 4), nullable=True)
    notional: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 4), nullable=True)
    limit_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 4), nullable=True)
    stop_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 4), nullable=True)
    time_in_force: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    status: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    filled_qty: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 4), nullable=True)
    filled_avg_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 4), nullable=True)
    submitted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    filled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    raw: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    account: Mapped["AlpacaAccount"] = relationship("AlpacaAccount", back_populates="orders")  # type: ignore[name-defined]
