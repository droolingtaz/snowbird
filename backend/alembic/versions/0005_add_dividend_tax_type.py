"""Add dividend_tax_type and dividend_tax_notes to instruments.

Revision ID: 0005
Revises: 0004
Create Date: 2026-05-12
"""
from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("instruments", sa.Column("dividend_tax_type", sa.String(64), nullable=True))
    op.add_column("instruments", sa.Column("dividend_tax_notes", sa.String(255), nullable=True))


def downgrade() -> None:
    op.drop_column("instruments", "dividend_tax_notes")
    op.drop_column("instruments", "dividend_tax_type")
