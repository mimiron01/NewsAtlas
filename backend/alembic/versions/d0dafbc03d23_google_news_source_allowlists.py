"""google news source allowlists (workspace + per-company)

Revision ID: d0dafbc03d23
Revises: 9b3c2f7a1d44
Create Date: 2026-07-21 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = 'd0dafbc03d23'
down_revision: Union[str, None] = '9b3c2f7a1d44'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'workspace_settings',
        sa.Column(
            'google_news_source_allowlist',
            postgresql.ARRAY(sa.String()),
            nullable=False,
            server_default='{}',
        ),
    )
    op.add_column(
        'target_companies',
        sa.Column(
            'google_news_source_allowlist',
            postgresql.ARRAY(sa.String()),
            nullable=False,
            server_default='{}',
        ),
    )
    # Drop server defaults once existing rows are backfilled by them — new rows get
    # their value from the ORM model default from here on (matches d4e8a2f6b913's
    # pattern for the sibling news-source-expansion migration).
    op.alter_column('workspace_settings', 'google_news_source_allowlist', server_default=None)
    op.alter_column('target_companies', 'google_news_source_allowlist', server_default=None)


def downgrade() -> None:
    op.drop_column('target_companies', 'google_news_source_allowlist')
    op.drop_column('workspace_settings', 'google_news_source_allowlist')
