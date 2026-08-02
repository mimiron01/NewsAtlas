"""theme_watches.exclude_terms: negative/exclude keyword filtering

Revision ID: c3d4e5f6a7b8
Revises: b93f7c04a1de
Create Date: 2026-08-02 00:00:00.000000

Additive-only: exclude_terms defaults to '{}' (empty array), so every existing topic's
query is byte-identical to today until a user opts in by adding an exclude term. See
docs/topics-ux-improvements-planning.html §1.2.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, None] = 'b93f7c04a1de'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'theme_watches',
        sa.Column(
            'exclude_terms',
            postgresql.ARRAY(sa.String()),
            nullable=False,
            server_default='{}',
        ),
    )
    op.alter_column('theme_watches', 'exclude_terms', server_default=None)


def downgrade() -> None:
    op.drop_column('theme_watches', 'exclude_terms')
