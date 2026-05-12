"""Bucket drift + rebalance algorithm."""
from decimal import Decimal

from app.models.bucket import Bucket, BucketHolding
from app.models.position import Position
from app.services.buckets import compute_drift


def _seed_portfolio(db, account):
    # 60% VTI target, 40% BND target. Actual: VTI $8000, BND $2000, total $10000
    db.add_all([
        Position(
            account_id=account.id, symbol="VTI",
            qty=Decimal("40"), avg_entry_price=Decimal("200"),
            market_value=Decimal("8000"), unrealized_pl=Decimal("0"),
            unrealized_plpc=Decimal("0"), current_price=Decimal("200"),
        ),
        Position(
            account_id=account.id, symbol="BND",
            qty=Decimal("25"), avg_entry_price=Decimal("80"),
            market_value=Decimal("2000"), unrealized_pl=Decimal("0"),
            unrealized_plpc=Decimal("0"), current_price=Decimal("80"),
        ),
    ])

    equity_bucket = Bucket(
        user_id=account.user_id, account_id=account.id, name="Equity",
        target_weight_pct=Decimal("60"), color="#3b82f6",
    )
    bonds_bucket = Bucket(
        user_id=account.user_id, account_id=account.id, name="Bonds",
        target_weight_pct=Decimal("40"), color="#f59e0b",
    )
    db.add_all([equity_bucket, bonds_bucket])
    db.flush()

    db.add_all([
        BucketHolding(bucket_id=equity_bucket.id, user_id=account.user_id,
                      account_id=account.id, symbol="VTI",
                      target_weight_within_bucket_pct=Decimal("100")),
        BucketHolding(bucket_id=bonds_bucket.id, user_id=account.user_id,
                      account_id=account.id, symbol="BND",
                      target_weight_within_bucket_pct=Decimal("100")),
    ])
    db.commit()


def test_drift_zero_when_on_target(db, demo_account):
    _seed_portfolio(db, demo_account)
    drifts = compute_drift(db, demo_account.id)

    by_name = {d.bucket_name: d for d in drifts}
    assert "Equity" in by_name and "Bonds" in by_name
    # Portfolio is exactly 80/20 actual vs 60/40 target: drifted.
    assert by_name["Equity"].actual_pct == pytest.approx(80.0, abs=0.01)
    assert by_name["Bonds"].actual_pct == pytest.approx(20.0, abs=0.01)
    assert by_name["Equity"].drift_pct == pytest.approx(20.0, abs=0.01)
    assert by_name["Bonds"].drift_pct == pytest.approx(-20.0, abs=0.01)


def test_drift_empty_account(db, demo_account):
    drifts = compute_drift(db, demo_account.id)
    assert drifts == []


def test_drift_effective_target_for_multi_holding_bucket(db, demo_account):
    # One bucket 100% target, two holdings 50/50 within bucket
    # Portfolio has only one of the two symbols -> drift visible
    db.add(Position(
        account_id=demo_account.id, symbol="VTI",
        qty=Decimal("50"), avg_entry_price=Decimal("200"),
        market_value=Decimal("10000"), unrealized_pl=Decimal("0"),
        unrealized_plpc=Decimal("0"), current_price=Decimal("200"),
    ))
    b = Bucket(user_id=demo_account.user_id, account_id=demo_account.id,
               name="All", target_weight_pct=Decimal("100"), color="#000")
    db.add(b); db.flush()
    db.add_all([
        BucketHolding(bucket_id=b.id, user_id=demo_account.user_id,
                      account_id=demo_account.id, symbol="VTI",
                      target_weight_within_bucket_pct=Decimal("50")),
        BucketHolding(bucket_id=b.id, user_id=demo_account.user_id,
                      account_id=demo_account.id, symbol="VXUS",
                      target_weight_within_bucket_pct=Decimal("50")),
    ])
    db.commit()

    drifts = compute_drift(db, demo_account.id)
    holdings = {h.symbol: h for h in drifts[0].holdings}
    # VTI effective target = 100 * 50 / 100 = 50
    assert holdings["VTI"].target_pct == pytest.approx(50.0, abs=0.01)
    # Actual VTI = 100% of portfolio -> drift +50
    assert holdings["VTI"].actual_pct == pytest.approx(100.0, abs=0.01)
    assert holdings["VTI"].drift_pct == pytest.approx(50.0, abs=0.01)
    # VXUS absent -> actual 0, drift -50
    assert holdings["VXUS"].actual_pct == pytest.approx(0.0, abs=0.01)
    assert holdings["VXUS"].drift_pct == pytest.approx(-50.0, abs=0.01)


# pytest.approx convenience
import pytest
