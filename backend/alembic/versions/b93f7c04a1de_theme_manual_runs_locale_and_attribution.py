"""per-theme manual runs, per-theme Google News locale, theme usage attribution

Revision ID: b93f7c04a1de
Revises: 806b173cb73e
Create Date: 2026-07-28 00:00:00.000000

Everything here is additive and nullable/defaulted, so an existing deployment upgrades
without touching a single existing row's meaning:

- theme_watches.google_news_country/language: NULL = inherit the workspace-wide setting,
  which is exactly the behavior every existing theme has today.
- theme_watches.last_manual_run_at: NULL = never manually run, so the first click on the
  new per-theme trigger is never blocked by a cooldown.
- ingestion_runs.theme_watch_id: NULL = an ordinary full run (companies + all themes),
  which is what every historical run was.
- news_source_usage_logs.theme_watch_id: NULL for every company-attributed call, past and
  future; only theme fetches set it.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b93f7c04a1de'
down_revision: Union[str, None] = '806b173cb73e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('theme_watches', sa.Column('google_news_country', sa.String(length=8), nullable=True))
    op.add_column('theme_watches', sa.Column('google_news_language', sa.String(length=8), nullable=True))
    op.add_column(
        'theme_watches', sa.Column('last_manual_run_at', sa.DateTime(timezone=True), nullable=True)
    )

    op.add_column('ingestion_runs', sa.Column('theme_watch_id', sa.UUID(), nullable=True))
    op.create_foreign_key(
        'fk_ingestion_runs_theme_watch_id',
        'ingestion_runs',
        'theme_watches',
        ['theme_watch_id'],
        ['id'],
        ondelete='SET NULL',
    )
    op.add_column('ingestion_runs', sa.Column('current_theme_name', sa.String(length=255), nullable=True))
    # Backfilled to 0 for historical runs, then the default is dropped so new rows take
    # their value from the ORM model — same convention as the theme columns added in
    # 806b173cb73e.
    op.add_column(
        'ingestion_runs', sa.Column('themes_total', sa.Integer(), nullable=False, server_default='0')
    )
    op.alter_column('ingestion_runs', 'themes_total', server_default=None)

    op.add_column('news_source_usage_logs', sa.Column('theme_watch_id', sa.UUID(), nullable=True))
    op.create_foreign_key(
        'fk_news_source_usage_logs_theme_watch_id',
        'news_source_usage_logs',
        'theme_watches',
        ['theme_watch_id'],
        ['id'],
        ondelete='SET NULL',
    )


def downgrade() -> None:
    op.drop_constraint(
        'fk_news_source_usage_logs_theme_watch_id', 'news_source_usage_logs', type_='foreignkey'
    )
    op.drop_column('news_source_usage_logs', 'theme_watch_id')

    op.drop_column('ingestion_runs', 'themes_total')
    op.drop_column('ingestion_runs', 'current_theme_name')
    op.drop_constraint('fk_ingestion_runs_theme_watch_id', 'ingestion_runs', type_='foreignkey')
    op.drop_column('ingestion_runs', 'theme_watch_id')

    op.drop_column('theme_watches', 'last_manual_run_at')
    op.drop_column('theme_watches', 'google_news_language')
    op.drop_column('theme_watches', 'google_news_country')
