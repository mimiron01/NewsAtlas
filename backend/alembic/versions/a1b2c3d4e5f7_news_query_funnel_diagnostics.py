"""Query text + funnel drop counters on news_source_usage_logs

Phase 0 of docs/google-news-quality-planning.html: make the fetch funnel visible
before changing it. Existing rows keep NULL query_text/drop_counts — they predate
the instrumentation and there is nothing to backfill them from.

Revision ID: a1b2c3d4e5f7
Revises: f6a7b8c9d0e1
Create Date: 2026-07-30 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = 'a1b2c3d4e5f7'
down_revision: Union[str, None] = 'f6a7b8c9d0e1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('news_source_usage_logs', sa.Column('query_text', sa.Text(), nullable=True))
    op.add_column(
        'news_source_usage_logs',
        sa.Column('articles_raw', sa.Integer(), nullable=False, server_default='0'),
    )
    op.alter_column('news_source_usage_logs', 'articles_raw', server_default=None)
    op.add_column(
        'news_source_usage_logs',
        sa.Column('drop_counts', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('news_source_usage_logs', 'drop_counts')
    op.drop_column('news_source_usage_logs', 'articles_raw')
    op.drop_column('news_source_usage_logs', 'query_text')
