"""workspace_settings.theme_match_min_relevance_score: enforce a relevance floor for topic matches

Revision ID: c4d5e6f7a8b9
Revises: b8c7d6e5f4a3
Create Date: 2026-08-04 12:00:00.000000

Every ThemeMatch that survives triage is persisted and shown today regardless of its
LLM-assigned relevance_score (1-5) — the score is used only for sort order (see
services/digest.py, api/dashboard.py), never as a filter. That is the direct root cause
of the "topic templates surface generic industry noise, not company-specific signals"
complaint: a score-1 "tangentially related, no outreach angle" match is just as visible
as a score-5 one. This adds an enforced floor, defaulting to 3 (the prompt's own
midpoint — see _THEME_SYSTEM_PROMPT in services/ai_client.py) so existing workspaces get
an immediate precision improvement without needing to configure anything, while staying
adjustable per workspace via Settings.

Additive-only, no data migration needed.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c4d5e6f7a8b9'
down_revision: Union[str, None] = 'b8c7d6e5f4a3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'workspace_settings',
        sa.Column('theme_match_min_relevance_score', sa.Integer(), nullable=False, server_default='3'),
    )
    op.alter_column('workspace_settings', 'theme_match_min_relevance_score', server_default=None)


def downgrade() -> None:
    op.drop_column('workspace_settings', 'theme_match_min_relevance_score')
