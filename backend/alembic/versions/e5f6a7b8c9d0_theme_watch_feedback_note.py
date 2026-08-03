"""theme_watches.ai_feedback_note: per-topic dismiss-pattern steering note

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-08-02 00:20:00.000000

Additive-only: ai_feedback_note defaults to '' (empty), so every existing topic's AI
prompts are byte-identical to today until enough dismissed-match history accumulates to
produce a note. Mirrors workspace_settings.ai_feedback_note (see 51cd451dd56d) but scoped
per-topic. See docs/topics-ux-improvements-planning.html §3.1.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e5f6a7b8c9d0'
down_revision: Union[str, None] = 'd4e5f6a7b8c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'theme_watches', sa.Column('ai_feedback_note', sa.Text(), nullable=False, server_default='')
    )
    op.alter_column('theme_watches', 'ai_feedback_note', server_default=None)


def downgrade() -> None:
    op.drop_column('theme_watches', 'ai_feedback_note')
