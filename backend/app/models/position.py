from datetime import datetime, timezone
from typing import Optional
from decimal import Decimal
from sqlalchemy import String, DateTime, Numeric, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class Position(Base):
    __tablename__ = "positions"
    __table_args__ = (UniqueConstraint("account_id", "symbol", name="uq_position_account_symbol"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("alpaca_accounts.id", ondelete="CASCADE"), nullable=False, index=True)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    qty: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    avg_entry_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 4), nullable=True)
    market_value: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 4), nullable=True)
    unrealized_pl: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 4), nullable=True)
    unrealized_plpc: Mapped[Optional[Decimal]] = mapped_column(Numeric(9, 4), nullable=True)
    current_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 4), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    account: Mapped["AlpacaAccount"] = relationship("AlpacaAccount", back_populates="positions")  # type: ignore[name-defined]
