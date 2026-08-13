"""ingestion runs: target_company_ids for company-scoped manual runs

Revision ID: b4c5d6e7f809
Revises: 6e7f8a9b0c1d
Create Date: 2026-08-13 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b4c5d6e7f809'
down_revision: Union[str, None] = '6e7f8a9b0c1d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('ingestion_runs', sa.Column('target_company_ids', sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column('ingestion_runs', 'target_company_ids')
