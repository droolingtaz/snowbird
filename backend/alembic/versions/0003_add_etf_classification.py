"""Add ETF classification columns to instruments.

Revision ID: 0003
Revises: 0002
Create Date: 2026-04-17
"""
from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("instruments", sa.Column("is_etf", sa.Boolean(), nullable=True, server_default="false"))
    op.add_column("instruments", sa.Column("etf_category", sa.String(100), nullable=True))


def downgrade() -> None:
    op.drop_column("instruments", "etf_category")
    op.drop_column("instruments", "is_etf")
