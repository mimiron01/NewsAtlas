"""Split term roles, add denylists, make allowlists overridable

Phase 2 of docs/google-news-quality-planning.html.

Two backfills carry the behaviour change without a cliff:

* context_terms := keywords. That is exactly the role keywords played in the Google query
  (name AND (kw…)), so every query is byte-identical the day this lands. aliases starts
  empty, which makes the grounding guard strictly *stricter* (it now requires the name)
  — the intended fix, not a regression. Copying keywords into aliases instead would have
  loosened every query overnight.
* allowlist := union(workspace, entity) where the entity already had one. Under the old
  union semantics an entity list was additive, so under the new override semantics it
  would silently narrow; backfilling the union keeps every effective query unchanged and
  leaves override semantics governing only what users change afterwards. Entities with an
  empty list become NULL, i.e. "inherit", which is what empty meant before.

Revision ID: c3d4e5f6a7b9
Revises: b2c3d4e5f6a8
Create Date: 2026-07-30 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c3d4e5f6a7b9'
down_revision: Union[str, None] = 'b2c3d4e5f6a8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'target_companies',
        sa.Column('aliases', sa.ARRAY(sa.String()), nullable=False, server_default='{}'),
    )
    op.add_column(
        'target_companies',
        sa.Column('context_terms', sa.ARRAY(sa.String()), nullable=False, server_default='{}'),
    )
    op.add_column(
        'target_companies',
        sa.Column('exclusion_terms', sa.ARRAY(sa.String()), nullable=False, server_default='{}'),
    )
    op.add_column(
        'target_companies',
        sa.Column(
            'google_news_source_denylist', sa.ARRAY(sa.String()), nullable=False, server_default='{}'
        ),
    )
    op.add_column(
        'target_companies',
        sa.Column(
            'google_news_require_name_in_title', sa.Boolean(), nullable=False, server_default='false'
        ),
    )
    op.add_column(
        'theme_watches',
        sa.Column('exclusion_terms', sa.ARRAY(sa.String()), nullable=False, server_default='{}'),
    )
    op.add_column(
        'theme_watches',
        sa.Column(
            'google_news_source_denylist', sa.ARRAY(sa.String()), nullable=False, server_default='{}'
        ),
    )
    op.add_column(
        'workspace_settings',
        sa.Column(
            'google_news_source_denylist', sa.ARRAY(sa.String()), nullable=False, server_default='{}'
        ),
    )
    op.add_column(
        'workspace_settings',
        sa.Column(
            'google_news_query_strategy', sa.String(length=16), nullable=False, server_default='single'
        ),
    )

    # Backfill 1: keywords keep doing what they already did, under their real name.
    op.execute("UPDATE target_companies SET context_terms = keywords")

    # Backfill 2: preserve each entity's *effective* allowlist before override semantics
    # take over. Done while the columns are still NOT NULL, so the union is computed from
    # the values as they stand today.
    op.execute(
        """
        UPDATE target_companies tc
        SET google_news_source_allowlist = sub.merged
        FROM (
            SELECT tc2.id,
                   ARRAY(
                       SELECT DISTINCT unnest(
                           COALESCE(ws.google_news_source_allowlist, '{}')
                           || COALESCE(tc2.google_news_source_allowlist, '{}')
                       )
                   ) AS merged
            FROM target_companies tc2
            CROSS JOIN (SELECT google_news_source_allowlist FROM workspace_settings LIMIT 1) ws
            WHERE array_length(tc2.google_news_source_allowlist, 1) > 0
        ) sub
        WHERE tc.id = sub.id
        """
    )
    op.execute(
        """
        UPDATE theme_watches tw
        SET google_news_source_allowlist = sub.merged
        FROM (
            SELECT tw2.id,
                   ARRAY(
                       SELECT DISTINCT unnest(
                           COALESCE(ws.google_news_source_allowlist, '{}')
                           || COALESCE(tw2.google_news_source_allowlist, '{}')
                       )
                   ) AS merged
            FROM theme_watches tw2
            CROSS JOIN (SELECT google_news_source_allowlist FROM workspace_settings LIMIT 1) ws
            WHERE array_length(tw2.google_news_source_allowlist, 1) > 0
        ) sub
        WHERE tw.id = sub.id
        """
    )

    # Now that effective lists are preserved, empty means "never set one" → inherit.
    op.alter_column('target_companies', 'google_news_source_allowlist', nullable=True)
    op.alter_column('theme_watches', 'google_news_source_allowlist', nullable=True)
    op.execute(
        "UPDATE target_companies SET google_news_source_allowlist = NULL "
        "WHERE array_length(google_news_source_allowlist, 1) IS NULL"
    )
    op.execute(
        "UPDATE theme_watches SET google_news_source_allowlist = NULL "
        "WHERE array_length(google_news_source_allowlist, 1) IS NULL"
    )

    for table, column in (
        ('target_companies', 'aliases'),
        ('target_companies', 'context_terms'),
        ('target_companies', 'exclusion_terms'),
        ('target_companies', 'google_news_source_denylist'),
        ('target_companies', 'google_news_require_name_in_title'),
        ('theme_watches', 'exclusion_terms'),
        ('theme_watches', 'google_news_source_denylist'),
        ('workspace_settings', 'google_news_source_denylist'),
        ('workspace_settings', 'google_news_query_strategy'),
    ):
        op.alter_column(table, column, server_default=None)


def downgrade() -> None:
    # NULL (inherit) collapses back to empty, which is what it meant under union
    # semantics. Terms that were split into aliases/context_terms are not merged back into
    # keywords: keywords was kept synchronized on every write, so it is already correct.
    op.execute(
        "UPDATE target_companies SET google_news_source_allowlist = '{}' "
        "WHERE google_news_source_allowlist IS NULL"
    )
    op.execute(
        "UPDATE theme_watches SET google_news_source_allowlist = '{}' "
        "WHERE google_news_source_allowlist IS NULL"
    )
    op.alter_column(
        'target_companies', 'google_news_source_allowlist', nullable=False, server_default='{}'
    )
    op.alter_column(
        'theme_watches', 'google_news_source_allowlist', nullable=False, server_default='{}'
    )

    op.drop_column('workspace_settings', 'google_news_query_strategy')
    op.drop_column('workspace_settings', 'google_news_source_denylist')
    op.drop_column('theme_watches', 'google_news_source_denylist')
    op.drop_column('theme_watches', 'exclusion_terms')
    op.drop_column('target_companies', 'google_news_require_name_in_title')
    op.drop_column('target_companies', 'google_news_source_denylist')
    op.drop_column('target_companies', 'exclusion_terms')
    op.drop_column('target_companies', 'context_terms')
    op.drop_column('target_companies', 'aliases')
