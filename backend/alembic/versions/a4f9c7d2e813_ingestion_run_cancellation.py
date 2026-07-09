"""ingestion run cancellation: cancel_requested flag

Revision ID: a4f9c7d2e813
Revises: 37ed1e25e7bb
Create Date: 2026-07-09 00:05:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a4f9c7d2e813'
down_revision: Union[str, None] = '37ed1e25e7bb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'ingestion_runs',
        sa.Column('cancel_requested', sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.alter_column('ingestion_runs', 'cancel_requested', server_default=None)


def downgrade() -> None:
    op.drop_column('ingestion_runs', 'cancel_requested')
