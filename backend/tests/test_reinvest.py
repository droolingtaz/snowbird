"""Dividend reinvestment: tax reserve + bucket-target distribution tests."""
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from unittest.mock import patch, MagicMock

import pytest

from app.models.activity import Activity
from app.models.bucket import Bucket, BucketHolding
from app.models.position import Position
from app.models.reinvest import DividendReinvestRun, DividendReinvestSettings
from app.services.reinvest import (
    ensure_tax_reserve_bucket,
    get_or_create_settings,
    get_unreinvested_dividend_cash,
    compute_reinvest_plan,
    execute_reinvest_plan,
    TAX_RESERVE_BUCKET_NAME,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _add_div_activities(db, account_id, amounts, base_time=None):
    """Seed DIV activities with given net_amount values."""
    if base_time is None:
        base_time = datetime.now(timezone.utc)
    for i, amt in enumerate(amounts):
        db.add(Activity(
            account_id=account_id,
            alpaca_id=f"div-{account_id}-{i}-{amt}",
            activity_type="DIV",
            symbol=f"ETF{i}",
            net_amount=Decimal(str(amt)),
            date=base_time.date(),
            created_at=base_time + timedelta(seconds=i),
        ))
    db.commit()


def _seed_buckets_and_positions(db, account):
    """Create a standard bucket setup for rebalance tests."""
    account_id = account.id
    user_id = account.user_id
    db.add_all([
        Position(
            account_id=account_id, symbol="VTI",
            qty=Decimal("50"), avg_entry_price=Decimal("200"),
            market_value=Decimal("10000"), unrealized_pl=Decimal("0"),
            unrealized_plpc=Decimal("0"), current_price=Decimal("200"),
        ),
        Position(
            account_id=account_id, symbol="BND",
            qty=Decimal("100"), avg_entry_price=Decimal("80"),
            market_value=Decimal("8000"), unrealized_pl=Decimal("0"),
            unrealized_plpc=Decimal("0"), current_price=Decimal("80"),
        ),
    ])

    equity = Bucket(
        user_id=user_id, account_id=account_id, name="Equity",
        target_weight_pct=Decimal("60"),
    )
    bonds = Bucket(
        user_id=user_id, account_id=account_id, name="Bonds",
        target_weight_pct=Decimal("40"),
    )
    db.add_all([equity, bonds])
    db.flush()

    db.add_all([
        BucketHolding(bucket_id=equity.id, user_id=user_id,
                      account_id=account_id, symbol="VTI",
                      target_weight_within_bucket_pct=Decimal("100")),
        BucketHolding(bucket_id=bonds.id, user_id=user_id,
                      account_id=account_id, symbol="BND",
                      target_weight_within_bucket_pct=Decimal("100")),
    ])
    db.commit()
    return equity, bonds


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_tax_reserve_bucket_idempotent(db, demo_account):
    """Calling ensure_tax_reserve_bucket twice creates only one bucket."""
    b1 = ensure_tax_reserve_bucket(db, demo_account.id, user_id=demo_account.user_id)
    b2 = ensure_tax_reserve_bucket(db, demo_account.id, user_id=demo_account.user_id)
    assert b1.id == b2.id
    assert b1.name == TAX_RESERVE_BUCKET_NAME
    assert float(b1.target_weight_pct) == 0.0
    assert len(b1.holdings) == 1
    assert b1.holdings[0].symbol == "CSHI"

    # Verify exactly one Tax Reserve bucket exists
    from sqlalchemy import select
    all_tax = db.execute(
        select(Bucket).where(
            Bucket.account_id == demo_account.id,
            Bucket.name == TAX_RESERVE_BUCKET_NAME,
        )
    ).scalars().all()
    assert len(all_tax) == 1


def test_tax_reserve_bucket_custom_symbol(db, demo_account):
    """Tax reserve bucket respects custom symbol."""
    b = ensure_tax_reserve_bucket(db, demo_account.id, symbol="BIL", user_id=demo_account.user_id)
    assert b.holdings[0].symbol == "BIL"


def test_compute_plan_24pct(db, demo_account):
    """$1000 dividends @ 24% -> $240 tax reserve, $760 investable."""
    _seed_buckets_and_positions(db, demo_account)
    settings = get_or_create_settings(db, demo_account.id)

    with patch("app.services.market_data.get_quote_cached") as mock_quote:
        mock_quote.return_value = {"last_price": 100.0}
        plan = compute_reinvest_plan(
            db, demo_account.id, Decimal("1000"), settings, demo_account,
        )

    assert plan.tax_reserved == pytest.approx(240.0)
    assert plan.investable == pytest.approx(760.0)
    assert plan.cshi_order is not None
    assert plan.cshi_order.symbol == "CSHI"
    assert plan.cshi_order.notional == pytest.approx(240.0)
    assert plan.cshi_order.purpose == "tax_reserve"
    assert len(plan.total_orders) >= 1  # at least the CSHI order


def test_compute_plan_zero_dividends(db, demo_account):
    """Zero dividend cash should produce empty plan."""
    settings = get_or_create_settings(db, demo_account.id)

    plan = compute_reinvest_plan(
        db, demo_account.id, Decimal("0"), settings, demo_account,
    )
    assert plan.tax_reserved == 0.0
    assert plan.investable == 0.0
    assert plan.cshi_order is None
    assert plan.investment_orders == []
    assert plan.total_orders == []


def test_compute_plan_excludes_tax_reserve_bucket(db, demo_account):
    """Tax reserve bucket (0% weight) should not pollute rebalance math."""
    _seed_buckets_and_positions(db, demo_account)
    ensure_tax_reserve_bucket(db, demo_account.id, user_id=demo_account.user_id)
    settings = get_or_create_settings(db, demo_account.id)

    with patch("app.services.market_data.get_quote_cached") as mock_quote:
        mock_quote.return_value = {"last_price": 100.0}
        plan = compute_reinvest_plan(
            db, demo_account.id, Decimal("1000"), settings, demo_account,
        )

    # Verify CSHI is NOT in investment_orders (only in cshi_order)
    inv_symbols = [o.symbol for o in plan.investment_orders]
    assert "CSHI" not in inv_symbols

    # All investment orders should have purpose="investment"
    for o in plan.investment_orders:
        assert o.purpose == "investment"


def test_execute_records_run(db, demo_account):
    """Successful execution writes a run row with status='executed'."""
    _seed_buckets_and_positions(db, demo_account)
    ensure_tax_reserve_bucket(db, demo_account.id, user_id=demo_account.user_id)
    settings = get_or_create_settings(db, demo_account.id)

    with patch("app.services.market_data.get_quote_cached") as mock_quote:
        mock_quote.return_value = {"last_price": 100.0}
        plan = compute_reinvest_plan(
            db, demo_account.id, Decimal("500"), settings, demo_account,
        )

    mock_order = MagicMock()
    mock_order.id = "mock-alpaca-id-1"
    mock_order.client_order_id = "mock-client-1"
    mock_order.status.value = "accepted"

    with patch("app.services.trading.place_order") as mock_place:
        mock_db_order = MagicMock()
        mock_db_order.id = 1
        mock_db_order.alpaca_id = "mock-alpaca-id-1"
        mock_place.return_value = mock_db_order

        run = execute_reinvest_plan(db, demo_account, plan, trigger="manual")

    assert run.status == "executed"
    assert run.trigger == "manual"
    assert float(run.dividend_cash_total) == pytest.approx(500.0)
    assert float(run.tax_reserved) == pytest.approx(120.0)
    assert float(run.invested) == pytest.approx(380.0)
    assert run.orders_json is not None
    assert len(run.orders_json["placed"]) > 0
    assert run.error is None


def test_execute_handles_partial_failure(db, demo_account):
    """If one order fails, status='failed' and error is captured."""
    _seed_buckets_and_positions(db, demo_account)
    ensure_tax_reserve_bucket(db, demo_account.id, user_id=demo_account.user_id)
    settings = get_or_create_settings(db, demo_account.id)

    with patch("app.services.market_data.get_quote_cached") as mock_quote:
        mock_quote.return_value = {"last_price": 100.0}
        plan = compute_reinvest_plan(
            db, demo_account.id, Decimal("1000"), settings, demo_account,
        )

    call_count = 0

    def side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # First order succeeds
            mock_result = MagicMock()
            mock_result.id = 1
            mock_result.alpaca_id = "ok-1"
            return mock_result
        else:
            # Subsequent orders fail
            raise RuntimeError("Alpaca API unavailable")

    with patch("app.services.trading.place_order", side_effect=side_effect):
        run = execute_reinvest_plan(db, demo_account, plan, trigger="manual")

    assert run.status == "failed"
    assert run.error is not None
    assert "Alpaca API unavailable" in run.error
    # First order was still placed
    assert len(run.orders_json["placed"]) >= 1
    assert len(run.orders_json["errors"]) >= 1


def test_unreinvested_cash_sums_div_activities(db, demo_account):
    """Unreinvested cash sums all DIV activities when no prior run."""
    _add_div_activities(db, demo_account.id, [100, 50.50, 25.25])
    cash = get_unreinvested_dividend_cash(db, demo_account.id)
    assert cash == Decimal("175.75")


def test_unreinvested_cash_excludes_prior_executed_runs(db, demo_account):
    """DIV activities before a prior executed run are not counted."""
    old_time = datetime.now(timezone.utc) - timedelta(days=7)
    _add_div_activities(db, demo_account.id, [100, 200], base_time=old_time)

    # Record an executed run after those activities
    run = DividendReinvestRun(
        account_id=demo_account.id,
        run_at=old_time + timedelta(days=1),
        trigger="manual",
        dividend_cash_total=Decimal("300"),
        tax_reserved=Decimal("72"),
        invested=Decimal("228"),
        status="executed",
    )
    db.add(run)
    db.commit()

    # New activities after the run
    new_time = datetime.now(timezone.utc)
    _add_div_activities(db, demo_account.id, [50, 30], base_time=new_time)

    # Only new activities should be counted
    cash = get_unreinvested_dividend_cash(db, demo_account.id)
    assert cash == Decimal("80")


def test_unreinvested_cash_ignores_non_executed_runs(db, demo_account):
    """Preview or failed runs should not exclude DIV activities."""
    old_time = datetime.now(timezone.utc) - timedelta(days=7)
    _add_div_activities(db, demo_account.id, [100], base_time=old_time)

    # A preview run (should be ignored)
    run = DividendReinvestRun(
        account_id=demo_account.id,
        run_at=old_time + timedelta(days=1),
        trigger="manual",
        dividend_cash_total=Decimal("100"),
        tax_reserved=Decimal("24"),
        invested=Decimal("76"),
        status="preview",
    )
    db.add(run)
    db.commit()

    cash = get_unreinvested_dividend_cash(db, demo_account.id)
    assert cash == Decimal("100")


def test_get_or_create_settings_defaults(db, demo_account):
    """Default settings are created with expected values."""
    settings = get_or_create_settings(db, demo_account.id)
    assert float(settings.tax_rate_pct) == pytest.approx(24.0)
    assert settings.tax_reserve_symbol == "CSHI"
    assert settings.auto_reinvest_enabled is False
    assert float(settings.auto_reinvest_threshold) == pytest.approx(50.0)


def test_get_or_create_settings_idempotent(db, demo_account):
    """Second call returns same row, not a duplicate."""
    s1 = get_or_create_settings(db, demo_account.id)
    s2 = get_or_create_settings(db, demo_account.id)
    assert s1.id == s2.id
