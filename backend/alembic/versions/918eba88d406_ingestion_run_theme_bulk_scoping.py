"""ingestion runs: theme_watch_ids for "fetch all my Themen" manual runs

Revision ID: 918eba88d406
Revises: b4c5d6e7f809
Create Date: 2026-08-18 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '918eba88d406'
down_revision: Union[str, None] = 'b4c5d6e7f809'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('ingestion_runs', sa.Column('theme_watch_ids', sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column('ingestion_runs', 'theme_watch_ids')
