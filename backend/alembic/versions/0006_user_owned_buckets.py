"""Move bucket ownership to user: add user_id, make account_id nullable.

Revision ID: 0006
Revises: 0005
Create Date: 2026-05-12
"""
from alembic import op
import sqlalchemy as sa

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- buckets ---

    # 1. Add user_id column (nullable first for backfill)
    op.add_column("buckets", sa.Column("user_id", sa.Integer(), nullable=True))

    # 2. Backfill user_id from the linked alpaca_account
    op.execute(
        "UPDATE buckets SET user_id = ("
        "  SELECT user_id FROM alpaca_accounts WHERE alpaca_accounts.id = buckets.account_id"
        ")"
    )

    # 3. Make user_id NOT NULL after backfill
    op.alter_column("buckets", "user_id", nullable=False)

    # 4. Add FK and index for user_id
    op.create_foreign_key(
        "buckets_user_id_fkey", "buckets", "users", ["user_id"], ["id"],
        ondelete="CASCADE",
    )
    op.create_index("ix_buckets_user_id", "buckets", ["user_id"])

    # 5. Drop old account_id FK (CASCADE), re-create as SET NULL with nullable column
    op.drop_constraint("buckets_account_id_fkey", "buckets", type_="foreignkey")
    op.alter_column("buckets", "account_id", nullable=True)
    op.create_foreign_key(
        "buckets_account_id_fkey", "buckets", "alpaca_accounts",
        ["account_id"], ["id"], ondelete="SET NULL",
    )

    # --- bucket_holdings ---

    # 1. Add user_id column (nullable first for backfill)
    op.add_column("bucket_holdings", sa.Column("user_id", sa.Integer(), nullable=True))

    # 2. Backfill user_id from parent bucket
    op.execute(
        "UPDATE bucket_holdings SET user_id = ("
        "  SELECT b.user_id FROM buckets b WHERE b.id = bucket_holdings.bucket_id"
        ")"
    )

    # 3. Make user_id NOT NULL
    op.alter_column("bucket_holdings", "user_id", nullable=False)

    # 4. FK + index
    op.create_foreign_key(
        "bucket_holdings_user_id_fkey", "bucket_holdings", "users",
        ["user_id"], ["id"], ondelete="CASCADE",
    )
    op.create_index("ix_bucket_holdings_user_id", "bucket_holdings", ["user_id"])


def downgrade() -> None:
    # --- bucket_holdings: remove user_id ---
    op.drop_index("ix_bucket_holdings_user_id", table_name="bucket_holdings")
    op.drop_constraint("bucket_holdings_user_id_fkey", "bucket_holdings", type_="foreignkey")
    op.drop_column("bucket_holdings", "user_id")

    # --- buckets: restore account_id NOT NULL + CASCADE, remove user_id ---
    op.drop_constraint("buckets_account_id_fkey", "buckets", type_="foreignkey")
    op.alter_column("buckets", "account_id", nullable=False)
    op.create_foreign_key(
        "buckets_account_id_fkey", "buckets", "alpaca_accounts",
        ["account_id"], ["id"], ondelete="CASCADE",
    )

    op.drop_index("ix_buckets_user_id", table_name="buckets")
    op.drop_constraint("buckets_user_id_fkey", "buckets", type_="foreignkey")
    op.drop_column("buckets", "user_id")
