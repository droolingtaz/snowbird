from datetime import datetime, timezone
from sqlalchemy import String, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    accounts: Mapped[list["AlpacaAccount"]] = relationship(  # type: ignore[name-defined]
        "AlpacaAccount", back_populates="user", cascade="all, delete-orphan"
    )
    buckets: Mapped[list["Bucket"]] = relationship(  # type: ignore[name-defined]
        "Bucket", back_populates="user", cascade="all, delete-orphan"
    )
