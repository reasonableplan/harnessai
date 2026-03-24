"""add epic_id to plans table

Revision ID: a1b2c3d4e5f6
Revises: 6655f15fca33
Create Date: 2026-03-24 00:00:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "6655f15fca33"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("plans", sa.Column("epic_id", sa.String(), nullable=False, server_default=""))


def downgrade() -> None:
    op.drop_column("plans", "epic_id")
