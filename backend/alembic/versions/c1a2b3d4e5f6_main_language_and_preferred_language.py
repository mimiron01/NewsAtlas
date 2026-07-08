"""workspace main_language + per-user preferred_language

Revision ID: c1a2b3d4e5f6
Revises: f2230b463357
Create Date: 2026-07-08 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c1a2b3d4e5f6'
down_revision: Union[str, None] = 'f2230b463357'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'workspace_settings',
        sa.Column('main_language', sa.String(length=8), nullable=False, server_default='en'),
    )
    op.add_column(
        'users',
        sa.Column('preferred_language', sa.String(length=8), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('users', 'preferred_language')
    op.drop_column('workspace_settings', 'main_language')
