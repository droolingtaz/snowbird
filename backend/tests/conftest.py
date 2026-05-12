"""Pytest fixtures: isolated in-memory SQLite DB with all tables."""
from __future__ import annotations

import os
import sys

# Make sure the app package is importable when running from repo root
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Force a predictable SECRET_KEY for Fernet/JWT before app.config loads
os.environ.setdefault("SECRET_KEY", "v7ErFlQxS3H9a6mM7f3tW8pK5rJ2n1Yc0oBxQwZyU8k=")
os.environ.setdefault("POSTGRES_HOST", "localhost")
os.environ.setdefault("POSTGRES_USER", "test")
os.environ.setdefault("POSTGRES_PASSWORD", "test")
os.environ.setdefault("POSTGRES_DB", "test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Import models so their metadata is registered
from app.db import Base
from app.models import user, account, instrument, position, order, activity, bucket, snapshot  # noqa: F401
from app.models import user_goal  # noqa: F401
from app.models import reinvest  # noqa: F401


@pytest.fixture()
def db():
    """Fresh in-memory SQLite DB per test."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = TestSession()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture()
def demo_account(db):
    """A seeded user + paper Alpaca account."""
    from app.models.user import User
    from app.models.account import AlpacaAccount
    from app.security import hash_password, encrypt_secret

    u = User(email="t@local", password_hash=hash_password("pw"))
    db.add(u)
    db.flush()

    acct = AlpacaAccount(
        user_id=u.id,
        label="paper",
        mode="paper",
        api_key="PKTEST",
        api_secret_enc=encrypt_secret("secret"),
        base_url="https://paper-api.alpaca.markets",
        active=True,
    )
    db.add(acct)
    db.commit()
    return acct
