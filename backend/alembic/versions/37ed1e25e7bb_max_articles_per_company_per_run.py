"""max_articles_per_company_per_run cap on workspace_settings

Revision ID: 37ed1e25e7bb
Revises: c1a2b3d4e5f6
Create Date: 2026-07-09 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '37ed1e25e7bb'
down_revision: Union[str, None] = 'c1a2b3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'workspace_settings',
        sa.Column('max_articles_per_company_per_run', sa.Integer(), nullable=False, server_default='10'),
    )
    op.alter_column('workspace_settings', 'max_articles_per_company_per_run', server_default=None)


def downgrade() -> None:
    op.drop_column('workspace_settings', 'max_articles_per_company_per_run')
