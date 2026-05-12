"""Model creation + relationships."""
from decimal import Decimal
from datetime import date

from app.models.user import User
from app.models.account import AlpacaAccount
from app.models.position import Position
from app.models.bucket import Bucket, BucketHolding
from app.models.snapshot import PortfolioSnapshot
from app.security import hash_password, encrypt_secret


def test_create_user(db):
    u = User(email="a@b.co", password_hash=hash_password("x"))
    db.add(u)
    db.commit()
    assert u.id is not None


def test_account_encrypted_secret_stored(db):
    u = User(email="a@b.co", password_hash=hash_password("x"))
    db.add(u); db.flush()
    a = AlpacaAccount(
        user_id=u.id, label="p", mode="paper",
        api_key="PK", api_secret_enc=encrypt_secret("real-secret"),
        base_url="https://paper-api.alpaca.markets", active=True,
    )
    db.add(a); db.commit()
    # ciphertext must not contain the plaintext
    assert "real-secret" not in a.api_secret_enc


def test_bucket_with_holdings(db, demo_account):
    b = Bucket(
        user_id=demo_account.user_id,
        account_id=demo_account.id,
        name="Core Equity",
        target_weight_pct=Decimal("60.0000"),
        color="#3b82f6",
    )
    db.add(b); db.flush()
    db.add_all([
        BucketHolding(bucket_id=b.id, user_id=demo_account.user_id,
                      symbol="VTI",
                      target_weight_within_bucket_pct=Decimal("70")),
        BucketHolding(bucket_id=b.id, user_id=demo_account.user_id,
                      symbol="VXUS",
                      target_weight_within_bucket_pct=Decimal("30")),
    ])
    db.commit()
    assert len(b.holdings) == 2
    assert sum(float(h.target_weight_within_bucket_pct) for h in b.holdings) == 100.0


def test_position_and_snapshot(db, demo_account):
    db.add(Position(
        account_id=demo_account.id, symbol="AAPL",
        qty=Decimal("10"), avg_entry_price=Decimal("150"),
        market_value=Decimal("1800"), unrealized_pl=Decimal("300"),
        unrealized_plpc=Decimal("0.2"), current_price=Decimal("180"),
    ))
    db.add(PortfolioSnapshot(
        account_id=demo_account.id, date=date(2026, 4, 15),
        equity=Decimal("10000"), cash=Decimal("2000"),
        long_market_value=Decimal("8000"), pnl=Decimal("123.45"),
    ))
    db.commit()
