"""initial schema

Revision ID: 0001
Revises:
Create Date: 2024-01-01 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Users
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    # Alpaca accounts
    op.create_table(
        "alpaca_accounts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("label", sa.String(100), nullable=False),
        sa.Column("mode", sa.Enum("paper", "live", name="accountmode"), nullable=False),
        sa.Column("api_key", sa.String(255), nullable=False),
        sa.Column("api_secret_enc", sa.String(512), nullable=False),
        sa.Column("base_url", sa.String(255), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_alpaca_accounts_user_id", "alpaca_accounts", ["user_id"])

    # Instruments
    op.create_table(
        "instruments",
        sa.Column("symbol", sa.String(20), nullable=False),
        sa.Column("name", sa.String(255), nullable=True),
        sa.Column("asset_class", sa.String(50), nullable=True),
        sa.Column("exchange", sa.String(50), nullable=True),
        sa.Column("currency", sa.String(10), nullable=True),
        sa.Column("sector", sa.String(100), nullable=True),
        sa.Column("industry", sa.String(100), nullable=True),
        sa.Column("dividend_yield", sa.Numeric(9, 4), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("symbol"),
    )

    # Positions
    op.create_table(
        "positions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("symbol", sa.String(20), nullable=False),
        sa.Column("qty", sa.Numeric(18, 4), nullable=False),
        sa.Column("avg_entry_price", sa.Numeric(18, 4), nullable=True),
        sa.Column("market_value", sa.Numeric(18, 4), nullable=True),
        sa.Column("unrealized_pl", sa.Numeric(18, 4), nullable=True),
        sa.Column("unrealized_plpc", sa.Numeric(9, 4), nullable=True),
        sa.Column("current_price", sa.Numeric(18, 4), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["alpaca_accounts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("account_id", "symbol", name="uq_position_account_symbol"),
    )
    op.create_index("ix_positions_account_id", "positions", ["account_id"])

    # Orders
    op.create_table(
        "orders",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("alpaca_id", sa.String(50), nullable=True),
        sa.Column("client_order_id", sa.String(100), nullable=True),
        sa.Column("symbol", sa.String(20), nullable=False),
        sa.Column("side", sa.String(10), nullable=False),
        sa.Column("type", sa.String(20), nullable=False),
        sa.Column("qty", sa.Numeric(18, 4), nullable=True),
        sa.Column("notional", sa.Numeric(18, 4), nullable=True),
        sa.Column("limit_price", sa.Numeric(18, 4), nullable=True),
        sa.Column("stop_price", sa.Numeric(18, 4), nullable=True),
        sa.Column("time_in_force", sa.String(10), nullable=True),
        sa.Column("status", sa.String(30), nullable=True),
        sa.Column("filled_qty", sa.Numeric(18, 4), nullable=True),
        sa.Column("filled_avg_price", sa.Numeric(18, 4), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("filled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("raw", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["alpaca_accounts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("alpaca_id"),
    )
    op.create_index("ix_orders_account_id", "orders", ["account_id"])
    op.create_index("ix_orders_alpaca_id", "orders", ["alpaca_id"])

    # Activities
    op.create_table(
        "activities",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("alpaca_id", sa.String(100), nullable=False),
        sa.Column("activity_type", sa.String(20), nullable=False),
        sa.Column("symbol", sa.String(20), nullable=True),
        sa.Column("qty", sa.Numeric(18, 4), nullable=True),
        sa.Column("price", sa.Numeric(18, 4), nullable=True),
        sa.Column("net_amount", sa.Numeric(18, 4), nullable=True),
        sa.Column("date", sa.Date(), nullable=True),
        sa.Column("raw", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["alpaca_accounts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("alpaca_id"),
    )
    op.create_index("ix_activities_account_id", "activities", ["account_id"])
    op.create_index("ix_activities_activity_type", "activities", ["activity_type"])
    op.create_index("ix_activities_symbol", "activities", ["symbol"])
    op.create_index("ix_activities_date", "activities", ["date"])

    # Buckets
    op.create_table(
        "buckets",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("target_weight_pct", sa.Numeric(9, 4), nullable=False),
        sa.Column("color", sa.String(20), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["account_id"], ["alpaca_accounts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_buckets_account_id", "buckets", ["account_id"])

    # Bucket holdings
    op.create_table(
        "bucket_holdings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("bucket_id", sa.Integer(), nullable=False),
        sa.Column("symbol", sa.String(20), nullable=False),
        sa.Column("target_weight_within_bucket_pct", sa.Numeric(9, 4), nullable=False),
        sa.ForeignKeyConstraint(["bucket_id"], ["buckets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_bucket_holdings_bucket_id", "bucket_holdings", ["bucket_id"])

    # Portfolio snapshots
    op.create_table(
        "portfolio_snapshots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("equity", sa.Numeric(18, 4), nullable=False),
        sa.Column("cash", sa.Numeric(18, 4), nullable=True),
        sa.Column("long_market_value", sa.Numeric(18, 4), nullable=True),
        sa.Column("pnl", sa.Numeric(18, 4), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["alpaca_accounts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("account_id", "date", name="uq_snapshot_account_date"),
    )
    op.create_index("ix_portfolio_snapshots_account_id", "portfolio_snapshots", ["account_id"])
    op.create_index("ix_portfolio_snapshots_date", "portfolio_snapshots", ["date"])


def downgrade() -> None:
    op.drop_table("portfolio_snapshots")
    op.drop_table("bucket_holdings")
    op.drop_table("buckets")
    op.drop_table("activities")
    op.drop_table("orders")
    op.drop_table("positions")
    op.drop_table("instruments")
    op.drop_table("alpaca_accounts")
    op.drop_table("users")
    op.execute("DROP TYPE IF EXISTS accountmode")
