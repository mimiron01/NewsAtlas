"""theme_follows.include_in_digest + theme_matches.emailed_at: opt-in topic digest

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-08-02 00:30:00.000000

Additive-only: include_in_digest defaults to false, so no existing digest changes shape
until a user explicitly opts a topic in. See
docs/topics-ux-improvements-planning.html §4.3.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f6a7b8c9d0e1'
down_revision: Union[str, None] = 'e5f6a7b8c9d0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'theme_follows',
        sa.Column('include_in_digest', sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.alter_column('theme_follows', 'include_in_digest', server_default=None)
    op.add_column('theme_matches', sa.Column('emailed_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('theme_matches', 'emailed_at')
    op.drop_column('theme_follows', 'include_in_digest')
