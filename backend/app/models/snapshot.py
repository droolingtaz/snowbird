from datetime import date, datetime, timezone
from typing import Optional
from decimal import Decimal
from sqlalchemy import Date, DateTime, Numeric, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class PortfolioSnapshot(Base):
    __tablename__ = "portfolio_snapshots"
    __table_args__ = (UniqueConstraint("account_id", "date", name="uq_snapshot_account_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("alpaca_accounts.id", ondelete="CASCADE"), nullable=False, index=True)
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    equity: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    cash: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 4), nullable=True)
    long_market_value: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 4), nullable=True)
    pnl: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 4), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    account: Mapped["AlpacaAccount"] = relationship("AlpacaAccount", back_populates="snapshots")  # type: ignore[name-defined]
