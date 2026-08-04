"""theme_match_favorites: per-user favoriting for theme-topic matches

Revision ID: b8c7d6e5f4a3
Revises: a9b8c7d6e5f4
Create Date: 2026-08-04 00:10:00.000000

Signals have had per-user favoriting (signal_favorites) for a while; ThemeMatch never
got the equivalent (see theme_match_queries.py's docstring: "no favorite/open-todo
annotation here (out of scope for v1)"). This table mirrors signal_favorites exactly so
a theme-topic match found on the Themen page or the dashboard's Top Themen-Signale panel
can be starred the same way a company signal can.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = 'b8c7d6e5f4a3'
down_revision: Union[str, None] = 'a9b8c7d6e5f4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'theme_match_favorites',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('theme_match_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['theme_match_id'], ['theme_matches.id'], ondelete='CASCADE'),
        sa.UniqueConstraint('user_id', 'theme_match_id', name='uq_theme_match_favorites_user_match'),
    )
    op.create_index(
        'ix_theme_match_favorites_user_id', 'theme_match_favorites', ['user_id'],
    )


def downgrade() -> None:
    op.drop_index('ix_theme_match_favorites_user_id', table_name='theme_match_favorites')
    op.drop_table('theme_match_favorites')
