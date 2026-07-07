"""signal favorites and todos: per-user favoriting and per-signal task lists

Revision ID: f1a2b3c4d5e6
Revises: d4e8a2f6b913
Create Date: 2026-07-07 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f1a2b3c4d5e6'
down_revision: Union[str, None] = 'd4e8a2f6b913'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'signal_favorites',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('signal_id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['signal_id'], ['signals.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'signal_id', name='uq_signal_favorites_user_signal'),
    )
    op.create_index(
        'ix_signal_favorites_user_id', 'signal_favorites', ['user_id'],
    )

    op.create_table(
        'signal_todos',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('signal_id', sa.UUID(), nullable=False),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('is_done', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['signal_id'], ['signals.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.alter_column('signal_todos', 'is_done', server_default=None)
    op.create_index(
        'ix_signal_todos_user_signal', 'signal_todos', ['user_id', 'signal_id'],
    )
    op.create_index(
        'ix_signal_todos_user_open', 'signal_todos', ['user_id', 'is_done'],
    )


def downgrade() -> None:
    op.drop_index('ix_signal_todos_user_open', table_name='signal_todos')
    op.drop_index('ix_signal_todos_user_signal', table_name='signal_todos')
    op.drop_table('signal_todos')

    op.drop_index('ix_signal_favorites_user_id', table_name='signal_favorites')
    op.drop_table('signal_favorites')
