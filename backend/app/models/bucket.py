from typing import Optional
from decimal import Decimal
from sqlalchemy import String, Numeric, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class Bucket(Base):
    __tablename__ = "buckets"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    account_id: Mapped[Optional[int]] = mapped_column(ForeignKey("alpaca_accounts.id", ondelete="SET NULL"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    target_weight_pct: Mapped[Decimal] = mapped_column(Numeric(9, 4), nullable=False)
    color: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    user: Mapped["User"] = relationship("User", back_populates="buckets")  # type: ignore[name-defined]
    account: Mapped[Optional["AlpacaAccount"]] = relationship("AlpacaAccount", back_populates="buckets")  # type: ignore[name-defined]
    holdings: Mapped[list["BucketHolding"]] = relationship(
        "BucketHolding", back_populates="bucket", cascade="all, delete-orphan"
    )


class BucketHolding(Base):
    __tablename__ = "bucket_holdings"

    id: Mapped[int] = mapped_column(primary_key=True)
    bucket_id: Mapped[int] = mapped_column(ForeignKey("buckets.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    account_id: Mapped[Optional[int]] = mapped_column(ForeignKey("alpaca_accounts.id", ondelete="SET NULL"), nullable=True, index=True)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    target_weight_within_bucket_pct: Mapped[Decimal] = mapped_column(Numeric(9, 4), nullable=False)

    bucket: Mapped["Bucket"] = relationship("Bucket", back_populates="holdings")
