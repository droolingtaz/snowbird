"""Tests for income goal CRUD and projection."""
from __future__ import annotations

from datetime import date, timedelta

from app.models.position import Position
from app.models.activity import Activity
from app.services.goals import get_goal, upsert_goal, compute_projection


def test_goal_returns_none_when_unset(db, demo_account):
    """No goal saved -> returns None."""
    result = get_goal(db, demo_account.user_id)
    assert result is None


def test_upsert_creates_goal(db, demo_account):
    """First upsert creates a new goal."""
    result = upsert_goal(db, demo_account.user_id, target_annual_income=50000)
    assert result.target_annual_income == 50000
    assert result.assumed_annual_growth_pct == 8.0
    assert result.assumed_monthly_contribution == 0.0
    assert result.id is not None


def test_upsert_updates_goal(db, demo_account):
    """Second upsert updates existing goal."""
    upsert_goal(db, demo_account.user_id, target_annual_income=50000)
    result = upsert_goal(
        db, demo_account.user_id,
        target_annual_income=75000,
        assumed_annual_growth_pct=10.0,
        assumed_monthly_contribution=500.0,
    )
    assert result.target_annual_income == 75000
    assert result.assumed_annual_growth_pct == 10.0
    assert result.assumed_monthly_contribution == 500.0


def test_projection_with_known_inputs(db, demo_account):
    """Projection math: $20k equity, 5% yield, 10% growth, target $2k."""
    upsert_goal(
        db, demo_account.user_id,
        target_annual_income=2000,
        assumed_annual_growth_pct=10.0,
        assumed_monthly_contribution=0.0,
    )

    pos = Position(
        account_id=demo_account.id, symbol="VTI",
        qty=100, avg_entry_price=180, market_value=20000, current_price=200,
    )
    db.add(pos)

    today = date.today()
    for i in range(4):
        db.add(Activity(
            account_id=demo_account.id,
            alpaca_id=f"div-proj-{i}",
            activity_type="DIV",
            symbol="VTI",
            qty=100,
            price=2.50,
            net_amount=250.0,
            date=today - timedelta(days=80 * (i + 1)),
        ))
    db.commit()

    result = compute_projection(db, demo_account.user_id, demo_account.id)
    assert result is not None
    assert result.current_equity == 20000.0
    assert result.current_annual_income == 1000.0
    assert result.current_yield_pct == 5.0
    assert result.eta_year is not None
    assert result.years_to_goal is not None
    assert result.years_to_goal <= 10


def test_projection_returns_none_without_goal(db, demo_account):
    """No goal set -> projection returns None."""
    result = compute_projection(db, demo_account.user_id, demo_account.id)
    assert result is None


def test_projection_with_contributions(db, demo_account):
    """Monthly contributions accelerate reaching the goal."""
    upsert_goal(
        db, demo_account.user_id,
        target_annual_income=2000,
        assumed_annual_growth_pct=10.0,
        assumed_monthly_contribution=500.0,
    )

    pos = Position(
        account_id=demo_account.id, symbol="VTI",
        qty=100, avg_entry_price=180, market_value=20000, current_price=200,
    )
    db.add(pos)
    today = date.today()
    for i in range(4):
        db.add(Activity(
            account_id=demo_account.id,
            alpaca_id=f"div-contrib-{i}",
            activity_type="DIV",
            symbol="VTI",
            qty=100,
            price=2.50,
            net_amount=250.0,
            date=today - timedelta(days=80 * (i + 1)),
        ))
    db.commit()

    result_with = compute_projection(db, demo_account.user_id, demo_account.id)
    assert result_with is not None
    assert result_with.years_to_goal is not None

    upsert_goal(
        db, demo_account.user_id,
        target_annual_income=2000,
        assumed_annual_growth_pct=10.0,
        assumed_monthly_contribution=0.0,
    )
    result_without = compute_projection(db, demo_account.user_id, demo_account.id)
    assert result_without is not None
    assert result_without.years_to_goal is not None

    assert result_with.years_to_goal <= result_without.years_to_goal
