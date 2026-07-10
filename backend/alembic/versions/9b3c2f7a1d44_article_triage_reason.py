"""articles.triage_reason: persisted reason from the triage LLM call

Revision ID: 9b3c2f7a1d44
Revises: a4f9c7d2e813
Create Date: 2026-07-10 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '9b3c2f7a1d44'
down_revision: Union[str, None] = 'a4f9c7d2e813'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('articles', sa.Column('triage_reason', sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column('articles', 'triage_reason')
