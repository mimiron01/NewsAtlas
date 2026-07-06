"""news source expansion: multi-source articles, rate limits, usage logs

Revision ID: d4e8a2f6b913
Revises: ac9f253eecea
Create Date: 2026-07-06 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = 'd4e8a2f6b913'
down_revision: Union[str, None] = 'ac9f253eecea'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


ARTICLE_SOURCE_VALUES = ('newsapi', 'google_news_rss', 'newsdata')


def upgrade() -> None:
    bind = op.get_bind()

    # Created once, explicitly, with checkfirst=True (same pattern as the user_role enum
    # in b582dced558e). Every column definition below that reuses this type passes
    # create_type=False so the DDL compiler doesn't attempt to CREATE TYPE a second time
    # when the type is used again for news_source_usage_logs.source.
    postgresql.ENUM(*ARTICLE_SOURCE_VALUES, name='article_source').create(bind, checkfirst=True)
    article_source_column = postgresql.ENUM(
        *ARTICLE_SOURCE_VALUES, name='article_source', create_type=False
    )

    op.add_column(
        'articles',
        sa.Column('source', article_source_column, nullable=False, server_default='newsapi'),
    )
    op.alter_column('articles', 'source', server_default=None)
    op.add_column('articles', sa.Column('full_content', sa.Text(), nullable=True))
    op.add_column('articles', sa.Column('external_sentiment', sa.String(length=32), nullable=True))
    op.add_column('articles', sa.Column('external_tags', postgresql.ARRAY(sa.String()), nullable=True))

    op.add_column(
        'target_companies',
        sa.Column('backfilled_at', sa.DateTime(timezone=True), nullable=True),
    )

    op.add_column(
        'workspace_settings',
        sa.Column('newsapi_enabled', sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column(
        'workspace_settings',
        sa.Column('newsapi_max_requests_per_day', sa.Integer(), nullable=False, server_default='100'),
    )
    op.add_column(
        'workspace_settings',
        sa.Column('google_news_rss_enabled', sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        'workspace_settings',
        sa.Column('google_news_rss_country', sa.String(length=8), nullable=False, server_default='US'),
    )
    op.add_column(
        'workspace_settings',
        sa.Column('google_news_rss_language', sa.String(length=8), nullable=False, server_default='en'),
    )
    op.add_column(
        'workspace_settings',
        sa.Column(
            'google_news_rss_max_requests_per_minute', sa.Integer(), nullable=False, server_default='20'
        ),
    )
    op.add_column(
        'workspace_settings',
        sa.Column('newsdata_enabled', sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        'workspace_settings',
        sa.Column('newsdata_api_key', sa.Text(), nullable=False, server_default=''),
    )
    op.add_column(
        'workspace_settings',
        sa.Column('newsdata_full_content_enabled', sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column(
        'workspace_settings',
        sa.Column('newsdata_use_native_dedupe', sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column(
        'workspace_settings',
        sa.Column('newsdata_backfill_days', sa.Integer(), nullable=False, server_default='0'),
    )
    op.add_column(
        'workspace_settings',
        sa.Column('newsdata_max_requests_per_day', sa.Integer(), nullable=False, server_default='200'),
    )
    op.add_column(
        'workspace_settings',
        sa.Column('newsdata_max_requests_per_minute', sa.Integer(), nullable=False, server_default='30'),
    )

    # Drop server defaults once existing rows are backfilled by them — new rows get their
    # value from the ORM model default from here on (matches ac9f253eecea's pattern).
    for column in (
        'newsapi_enabled', 'newsapi_max_requests_per_day', 'google_news_rss_enabled',
        'google_news_rss_country', 'google_news_rss_language',
        'google_news_rss_max_requests_per_minute', 'newsdata_enabled', 'newsdata_api_key',
        'newsdata_full_content_enabled', 'newsdata_use_native_dedupe',
        'newsdata_backfill_days', 'newsdata_max_requests_per_day',
        'newsdata_max_requests_per_minute',
    ):
        op.alter_column('workspace_settings', column, server_default=None)

    op.create_table(
        'news_source_usage_logs',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('source', article_source_column, nullable=False),
        sa.Column('call_type', sa.String(length=16), nullable=False, server_default='latest'),
        sa.Column('target_company_id', sa.UUID(), nullable=True),
        sa.Column('requests_used', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('articles_returned', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['target_company_id'], ['target_companies.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    op.drop_table('news_source_usage_logs')

    op.drop_column('workspace_settings', 'newsdata_max_requests_per_minute')
    op.drop_column('workspace_settings', 'newsdata_max_requests_per_day')
    op.drop_column('workspace_settings', 'newsdata_backfill_days')
    op.drop_column('workspace_settings', 'newsdata_use_native_dedupe')
    op.drop_column('workspace_settings', 'newsdata_full_content_enabled')
    op.drop_column('workspace_settings', 'newsdata_api_key')
    op.drop_column('workspace_settings', 'newsdata_enabled')
    op.drop_column('workspace_settings', 'google_news_rss_max_requests_per_minute')
    op.drop_column('workspace_settings', 'google_news_rss_language')
    op.drop_column('workspace_settings', 'google_news_rss_country')
    op.drop_column('workspace_settings', 'google_news_rss_enabled')
    op.drop_column('workspace_settings', 'newsapi_max_requests_per_day')
    op.drop_column('workspace_settings', 'newsapi_enabled')

    op.drop_column('target_companies', 'backfilled_at')

    op.drop_column('articles', 'external_tags')
    op.drop_column('articles', 'external_sentiment')
    op.drop_column('articles', 'full_content')
    op.drop_column('articles', 'source')

    postgresql.ENUM(name='article_source').drop(op.get_bind(), checkfirst=True)
