from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import String, DateTime, Boolean, ForeignKey, Enum
from sqlalchemy.orm import Mapped, mapped_column, relationship
import enum

from app.db import Base


class AccountMode(str, enum.Enum):
    paper = "paper"
    live = "live"


class AlpacaAccount(Base):
    __tablename__ = "alpaca_accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    label: Mapped[str] = mapped_column(String(100), nullable=False)
    mode: Mapped[AccountMode] = mapped_column(Enum(AccountMode), nullable=False, default=AccountMode.paper)
    api_key: Mapped[str] = mapped_column(String(255), nullable=False)
    api_secret_enc: Mapped[str] = mapped_column(String(512), nullable=False)
    base_url: Mapped[str] = mapped_column(String(255), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_sync_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    user: Mapped["User"] = relationship("User", back_populates="accounts")  # type: ignore[name-defined]
    positions: Mapped[list["Position"]] = relationship(  # type: ignore[name-defined]
        "Position", back_populates="account", cascade="all, delete-orphan"
    )
    orders: Mapped[list["Order"]] = relationship(  # type: ignore[name-defined]
        "Order", back_populates="account", cascade="all, delete-orphan"
    )
    activities: Mapped[list["Activity"]] = relationship(  # type: ignore[name-defined]
        "Activity", back_populates="account", cascade="all, delete-orphan"
    )
    buckets: Mapped[list["Bucket"]] = relationship(  # type: ignore[name-defined]
        "Bucket", back_populates="account",
    )
    snapshots: Mapped[list["PortfolioSnapshot"]] = relationship(  # type: ignore[name-defined]
        "PortfolioSnapshot", back_populates="account", cascade="all, delete-orphan"
    )
