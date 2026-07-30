"""Per-company Google News edition + workspace time-operator toggle

Phase 1 of docs/google-news-quality-planning.html. The edition columns are nullable
with NULL meaning "inherit the workspace edition", matching theme_watches — so existing
companies keep exactly the behaviour they have today until someone sets one.

Revision ID: b2c3d4e5f6a8
Revises: a1b2c3d4e5f7
Create Date: 2026-07-30 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b2c3d4e5f6a8'
down_revision: Union[str, None] = 'a1b2c3d4e5f7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('target_companies', sa.Column('google_news_country', sa.String(length=8), nullable=True))
    op.add_column('target_companies', sa.Column('google_news_language', sa.String(length=8), nullable=True))
    op.add_column(
        'workspace_settings',
        sa.Column(
            'google_news_time_operator_enabled', sa.Boolean(), nullable=False, server_default='true'
        ),
    )
    op.alter_column('workspace_settings', 'google_news_time_operator_enabled', server_default=None)


def downgrade() -> None:
    op.drop_column('workspace_settings', 'google_news_time_operator_enabled')
    op.drop_column('target_companies', 'google_news_language')
    op.drop_column('target_companies', 'google_news_country')
