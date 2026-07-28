"""theme/topic search: theme_watches, theme_follows, theme_matches

Revision ID: 806b173cb73e
Revises: fe46f8cfc9d5
Create Date: 2026-07-23 00:00:00.000000

See docs/theme-search-planning.html. ThemeMatch reuses the existing article_source and
signal_status enum types (create_type=False) rather than creating duplicates.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = '806b173cb73e'
down_revision: Union[str, None] = 'fe46f8cfc9d5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    article_source_column = postgresql.ENUM(
        'newsapi', 'google_news_rss', 'newsdata', name='article_source', create_type=False
    )
    signal_status_column = postgresql.ENUM(
        'NEW', 'REVIEWED', 'ARCHIVED', 'DISMISSED', name='signal_status', create_type=False
    )

    op.create_table(
        'theme_watches',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('query_terms', postgresql.ARRAY(sa.String()), nullable=False),
        sa.Column('industry', sa.String(length=255), nullable=True),
        sa.Column('google_news_source_allowlist', postgresql.ARRAY(sa.String()), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('created_by', sa.UUID(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )

    op.create_table(
        'theme_follows',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('theme_watch_id', sa.UUID(), nullable=False),
        sa.Column('is_muted', sa.Boolean(), nullable=False),
        sa.Column('assigned_by', sa.UUID(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['theme_watch_id'], ['theme_watches.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['assigned_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'theme_watch_id', name='uq_theme_follows_user_theme'),
    )

    op.create_table(
        'theme_matches',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('theme_watch_id', sa.UUID(), nullable=False),
        sa.Column('source', article_source_column, nullable=False, server_default='google_news_rss'),
        sa.Column('source_name', sa.String(length=255), nullable=False),
        sa.Column('title', sa.Text(), nullable=False),
        sa.Column('url', sa.Text(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('published_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('fetched_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('embedding', postgresql.ARRAY(sa.Float()), nullable=True),
        sa.Column('duplicate_of_match_id', sa.UUID(), nullable=True),
        sa.Column('extracted_company_name', sa.String(length=255), nullable=True),
        sa.Column('matched_target_company_id', sa.UUID(), nullable=True),
        sa.Column('summary', sa.Text(), nullable=True),
        sa.Column('business_relevance', sa.Text(), nullable=True),
        sa.Column('supporting_quote', sa.Text(), nullable=True),
        sa.Column('relevance_score', sa.Integer(), nullable=True),
        sa.Column('signal_type', sa.Text(), nullable=True),
        sa.Column('confidence', sa.Text(), nullable=True),
        sa.Column('entities', sa.JSON(), nullable=True),
        sa.Column('status', signal_status_column, nullable=False, server_default='NEW'),
        sa.Column('skip_reason', sa.String(length=32), nullable=True),
        sa.Column('triage_reason', sa.String(length=255), nullable=True),
        sa.Column('prompt_tokens', sa.Integer(), nullable=True),
        sa.Column('completion_tokens', sa.Integer(), nullable=True),
        sa.Column('total_tokens', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['theme_watch_id'], ['theme_watches.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['duplicate_of_match_id'], ['theme_matches.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['matched_target_company_id'], ['target_companies.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_theme_matches_url', 'theme_matches', ['url'], unique=True)
    # Drop server defaults once existing rows (none yet, but matches convention) are
    # backfilled by them — new rows get their value from the ORM model default from here on.
    op.alter_column('theme_matches', 'source', server_default=None)
    op.alter_column('theme_matches', 'status', server_default=None)

    op.add_column(
        'workspace_settings',
        sa.Column('max_articles_per_theme_per_run', sa.Integer(), nullable=False, server_default='10'),
    )
    op.add_column(
        'workspace_settings',
        sa.Column('max_active_theme_watches', sa.Integer(), nullable=False, server_default='10'),
    )
    op.alter_column('workspace_settings', 'max_articles_per_theme_per_run', server_default=None)
    op.alter_column('workspace_settings', 'max_active_theme_watches', server_default=None)

    op.add_column(
        'ingestion_runs',
        sa.Column('theme_matches_created', sa.Integer(), nullable=False, server_default='0'),
    )
    op.add_column(
        'ingestion_runs',
        sa.Column('themes_processed', sa.Integer(), nullable=False, server_default='0'),
    )
    op.alter_column('ingestion_runs', 'theme_matches_created', server_default=None)
    op.alter_column('ingestion_runs', 'themes_processed', server_default=None)


def downgrade() -> None:
    op.drop_column('ingestion_runs', 'themes_processed')
    op.drop_column('ingestion_runs', 'theme_matches_created')

    op.drop_column('workspace_settings', 'max_active_theme_watches')
    op.drop_column('workspace_settings', 'max_articles_per_theme_per_run')

    op.drop_index('ix_theme_matches_url', table_name='theme_matches')
    op.drop_table('theme_matches')
    op.drop_table('theme_follows')
    op.drop_table('theme_watches')
