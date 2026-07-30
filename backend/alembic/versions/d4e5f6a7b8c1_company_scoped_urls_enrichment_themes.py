"""Company-scoped article URLs, enrichment columns, multi-provider themes

Phases 3, 4 and 6 of docs/google-news-quality-planning.html.

The unique-constraint move is the only irreversible part: existing rows all satisfy the
weaker constraint so the upgrade needs no cleanup, but once two companies hold the same
URL the global constraint can no longer be recreated. The downgrade says so rather than
pretending it round-trips.

Revision ID: d4e5f6a7b8c1
Revises: c3d4e5f6a7b9
Create Date: 2026-07-30 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd4e5f6a7b8c1'
down_revision: Union[str, None] = 'c3d4e5f6a7b9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- Phase 3: a story naming two tracked companies belongs to both ---
    # Uniqueness came from a unique *index* (ix_articles_url), not a table constraint, so
    # it's replaced by a plain index plus a composite constraint. The plain index is kept:
    # the theme path still looks URLs up globally.
    op.drop_index('ix_articles_url', table_name='articles')
    op.create_index('ix_articles_url', 'articles', ['url'], unique=False)
    op.create_unique_constraint('uq_articles_company_url', 'articles', ['target_company_id', 'url'])

    # --- Phase 4: enrichment ---
    op.add_column('articles', sa.Column('canonical_url', sa.Text(), nullable=True))
    op.add_column(
        'articles',
        sa.Column('content_enriched', sa.Boolean(), nullable=False, server_default='false'),
    )
    op.add_column('theme_matches', sa.Column('canonical_url', sa.Text(), nullable=True))
    op.add_column(
        'theme_matches',
        sa.Column('content_enriched', sa.Boolean(), nullable=False, server_default='false'),
    )
    op.add_column('theme_matches', sa.Column('full_content', sa.Text(), nullable=True))
    op.add_column(
        'workspace_settings',
        sa.Column(
            'google_news_resolve_urls_enabled', sa.Boolean(), nullable=False, server_default='false'
        ),
    )
    op.add_column(
        'workspace_settings',
        sa.Column(
            'google_news_fetch_snippets_enabled', sa.Boolean(), nullable=False, server_default='false'
        ),
    )
    op.add_column(
        'workspace_settings',
        sa.Column('max_enrichment_fetches_per_run', sa.Integer(), nullable=False, server_default='50'),
    )
    op.add_column(
        'workspace_settings',
        sa.Column('max_enrichment_seconds_per_run', sa.Integer(), nullable=False, server_default='120'),
    )

    # --- Phase 6: multi-provider themes ---
    # Default is Google News RSS alone: exactly the behaviour themes had before, so
    # nothing changes until an admin opts a workspace (or a theme) into more.
    op.add_column(
        'workspace_settings',
        sa.Column(
            'theme_news_sources',
            sa.ARRAY(sa.String()),
            nullable=False,
            server_default='{google_news_rss}',
        ),
    )
    op.add_column(
        'workspace_settings',
        sa.Column(
            'max_theme_requests_per_run_per_source', sa.Integer(), nullable=False, server_default='0'
        ),
    )
    op.add_column('theme_watches', sa.Column('news_sources', sa.ARRAY(sa.String()), nullable=True))

    for table, column in (
        ('articles', 'content_enriched'),
        ('theme_matches', 'content_enriched'),
        ('workspace_settings', 'google_news_resolve_urls_enabled'),
        ('workspace_settings', 'google_news_fetch_snippets_enabled'),
        ('workspace_settings', 'max_enrichment_fetches_per_run'),
        ('workspace_settings', 'max_enrichment_seconds_per_run'),
        ('workspace_settings', 'theme_news_sources'),
        ('workspace_settings', 'max_theme_requests_per_run_per_source'),
    ):
        op.alter_column(table, column, server_default=None)


def downgrade() -> None:
    op.drop_column('theme_watches', 'news_sources')
    op.drop_column('workspace_settings', 'max_theme_requests_per_run_per_source')
    op.drop_column('workspace_settings', 'theme_news_sources')
    op.drop_column('workspace_settings', 'max_enrichment_seconds_per_run')
    op.drop_column('workspace_settings', 'max_enrichment_fetches_per_run')
    op.drop_column('workspace_settings', 'google_news_fetch_snippets_enabled')
    op.drop_column('workspace_settings', 'google_news_resolve_urls_enabled')
    op.drop_column('theme_matches', 'full_content')
    op.drop_column('theme_matches', 'content_enriched')
    op.drop_column('theme_matches', 'canonical_url')
    op.drop_column('articles', 'content_enriched')
    op.drop_column('articles', 'canonical_url')

    # NOTE: this fails if any URL is now held by more than one company — which is the
    # whole point of the upgrade. Deduplicate manually before downgrading; there is no
    # safe automatic choice about which company's article to delete.
    op.drop_constraint('uq_articles_company_url', 'articles', type_='unique')
    op.drop_index('ix_articles_url', table_name='articles')
    op.create_index('ix_articles_url', 'articles', ['url'], unique=True)
