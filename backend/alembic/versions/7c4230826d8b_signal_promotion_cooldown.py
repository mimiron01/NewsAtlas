"""cooldown bookkeeping for the manual skipped-article signal promotion trigger

Revision ID: 7c4230826d8b
Revises: d0dafbc03d23
Create Date: 2026-07-21 00:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '7c4230826d8b'
down_revision: Union[str, None] = 'd0dafbc03d23'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'workspace_settings',
        sa.Column('last_manual_signal_promotion_at', sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('workspace_settings', 'last_manual_signal_promotion_at')
