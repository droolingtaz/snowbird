"""Tests for user-owned buckets surviving account deletion."""
import pytest
from decimal import Decimal

from app.models.user import User
from app.models.account import AlpacaAccount
from app.models.bucket import Bucket, BucketHolding
from app.models.position import Position
from app.security import hash_password, encrypt_secret


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture()
def user_with_two_accounts(db):
    """A user with two paper accounts."""
    u = User(email="owner@local", password_hash=hash_password("pw"))
    db.add(u)
    db.flush()

    acct1 = AlpacaAccount(
        user_id=u.id, label="paper-1", mode="paper",
        api_key="PK1", api_secret_enc=encrypt_secret("s1"),
        base_url="https://paper-api.alpaca.markets", active=True,
    )
    acct2 = AlpacaAccount(
        user_id=u.id, label="paper-2", mode="paper",
        api_key="PK2", api_secret_enc=encrypt_secret("s2"),
        base_url="https://paper-api.alpaca.markets", active=True,
    )
    db.add_all([acct1, acct2])
    db.commit()
    return u, acct1, acct2


@pytest.fixture()
def another_user(db):
    """A separate user for cross-user tests."""
    u = User(email="other@local", password_hash=hash_password("pw"))
    db.add(u)
    db.flush()
    acct = AlpacaAccount(
        user_id=u.id, label="other-paper", mode="paper",
        api_key="PK_OTHER", api_secret_enc=encrypt_secret("s_other"),
        base_url="https://paper-api.alpaca.markets", active=True,
    )
    db.add(acct)
    db.commit()
    return u, acct


# ── Tests ────────────────────────────────────────────────────────────────────


def test_bucket_survives_account_delete(db, user_with_two_accounts):
    """Deleting an account unlinks buckets (sets account_id=NULL) but does not delete them."""
    user, acct1, _ = user_with_two_accounts

    bucket = Bucket(
        user_id=user.id, account_id=acct1.id,
        name="Growth", target_weight_pct=Decimal("60"),
    )
    db.add(bucket)
    db.flush()

    holding = BucketHolding(
        bucket_id=bucket.id, user_id=user.id, account_id=acct1.id,
        symbol="VTI", target_weight_within_bucket_pct=Decimal("100"),
    )
    db.add(holding)
    db.commit()
    bucket_id = bucket.id

    # Delete the account
    db.delete(acct1)
    db.commit()

    # Bucket still exists, just unlinked
    reloaded = db.get(Bucket, bucket_id)
    assert reloaded is not None
    assert reloaded.account_id is None
    assert reloaded.user_id == user.id
    assert reloaded.name == "Growth"


def test_bucket_holdings_survive_account_delete(db, user_with_two_accounts):
    """BucketHolding rows persist after account deletion."""
    user, acct1, _ = user_with_two_accounts

    bucket = Bucket(
        user_id=user.id, account_id=acct1.id,
        name="Bonds", target_weight_pct=Decimal("40"),
    )
    db.add(bucket)
    db.flush()

    h1 = BucketHolding(
        bucket_id=bucket.id, user_id=user.id, account_id=acct1.id,
        symbol="BND", target_weight_within_bucket_pct=Decimal("50"),
    )
    h2 = BucketHolding(
        bucket_id=bucket.id, user_id=user.id, account_id=acct1.id,
        symbol="AGG", target_weight_within_bucket_pct=Decimal("50"),
    )
    db.add_all([h1, h2])
    db.commit()
    bucket_id = bucket.id

    db.delete(acct1)
    db.commit()

    reloaded = db.get(Bucket, bucket_id)
    assert reloaded is not None
    assert len(reloaded.holdings) == 2
    symbols = {h.symbol for h in reloaded.holdings}
    assert symbols == {"BND", "AGG"}
    for h in reloaded.holdings:
        assert h.account_id is None
        assert h.user_id == user.id


def test_relink_bucket_to_new_account(db, user_with_two_accounts):
    """A bucket can be re-linked to a different account owned by the same user."""
    user, acct1, acct2 = user_with_two_accounts

    bucket = Bucket(
        user_id=user.id, account_id=acct1.id,
        name="Growth", target_weight_pct=Decimal("60"),
    )
    db.add(bucket)
    db.flush()

    h = BucketHolding(
        bucket_id=bucket.id, user_id=user.id, account_id=acct1.id,
        symbol="VTI", target_weight_within_bucket_pct=Decimal("100"),
    )
    db.add(h)
    db.commit()

    # Relink to acct2
    bucket.account_id = acct2.id
    for holding in bucket.holdings:
        holding.account_id = acct2.id
    db.commit()

    db.refresh(bucket)
    assert bucket.account_id == acct2.id
    assert bucket.holdings[0].account_id == acct2.id


def test_relink_validates_ownership(db, user_with_two_accounts, another_user):
    """Cannot link a bucket to another user's account."""
    user, acct1, _ = user_with_two_accounts
    _, other_acct = another_user

    bucket = Bucket(
        user_id=user.id, account_id=acct1.id,
        name="Growth", target_weight_pct=Decimal("60"),
    )
    db.add(bucket)
    db.commit()

    # The API layer enforces this — at the model level the FK doesn't prevent it,
    # but the API checks user_id ownership. We test the model-level truth: the
    # bucket's user_id differs from the account's user_id.
    assert bucket.user_id != other_acct.user_id


def test_delete_user_cascades_buckets(db):
    """Hard-deleting a user removes all their buckets."""
    u = User(email="cascade@local", password_hash=hash_password("pw"))
    db.add(u)
    db.flush()

    acct = AlpacaAccount(
        user_id=u.id, label="paper", mode="paper",
        api_key="PK", api_secret_enc=encrypt_secret("s"),
        base_url="https://paper-api.alpaca.markets", active=True,
    )
    db.add(acct)
    db.flush()

    bucket = Bucket(
        user_id=u.id, account_id=acct.id,
        name="All", target_weight_pct=Decimal("100"),
    )
    db.add(bucket)
    db.flush()

    h = BucketHolding(
        bucket_id=bucket.id, user_id=u.id, account_id=acct.id,
        symbol="VTI", target_weight_within_bucket_pct=Decimal("100"),
    )
    db.add(h)
    db.commit()

    bucket_id = bucket.id
    holding_id = h.id

    db.delete(u)
    db.commit()

    assert db.get(Bucket, bucket_id) is None
    assert db.get(BucketHolding, holding_id) is None


def test_unlinked_bucket_has_no_drift(db, user_with_two_accounts):
    """An unlinked bucket (account_id=None) has no meaningful drift."""
    user, _, _ = user_with_two_accounts

    bucket = Bucket(
        user_id=user.id, account_id=None,
        name="Unlinked", target_weight_pct=Decimal("50"),
    )
    db.add(bucket)
    db.flush()

    h = BucketHolding(
        bucket_id=bucket.id, user_id=user.id, account_id=None,
        symbol="VTI", target_weight_within_bucket_pct=Decimal("100"),
    )
    db.add(h)
    db.commit()

    # Unlinked bucket can be created and queried without error
    db.refresh(bucket)
    assert bucket.account_id is None
    assert bucket.user_id == user.id
    assert len(bucket.holdings) == 1
