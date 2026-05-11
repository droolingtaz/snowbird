"""Add dividend reinvest settings and runs tables.

Revision ID: 0004
Revises: 0003
Create Date: 2026-05-11
"""
from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "dividend_reinvest_settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("account_id", sa.Integer(), sa.ForeignKey("alpaca_accounts.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("tax_rate_pct", sa.Numeric(9, 4), nullable=False, server_default="24.0000"),
        sa.Column("tax_reserve_symbol", sa.String(20), nullable=False, server_default="CSHI"),
        sa.Column("auto_reinvest_enabled", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("auto_reinvest_threshold", sa.Numeric(18, 4), nullable=False, server_default="50.0000"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "dividend_reinvest_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("account_id", sa.Integer(), sa.ForeignKey("alpaca_accounts.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("run_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("trigger", sa.String(20), nullable=False),
        sa.Column("dividend_cash_total", sa.Numeric(18, 4), nullable=False),
        sa.Column("tax_reserved", sa.Numeric(18, 4), nullable=False),
        sa.Column("invested", sa.Numeric(18, 4), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("orders_json", sa.JSON(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("dividend_reinvest_runs")
    op.drop_table("dividend_reinvest_settings")
