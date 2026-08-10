"""drop ingestion_interval_hours from workspace_settings

Revision ID: 5d61bc93aef9
Revises: d5e6f7a8b9c0
Create Date: 2026-08-10 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '5d61bc93aef9'
down_revision: Union[str, None] = 'd5e6f7a8b9c0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column('workspace_settings', 'ingestion_interval_hours')


def downgrade() -> None:
    op.add_column(
        'workspace_settings',
        sa.Column('ingestion_interval_hours', sa.Integer(), nullable=False, server_default='6'),
    )
    op.alter_column('workspace_settings', 'ingestion_interval_hours', server_default=None)
