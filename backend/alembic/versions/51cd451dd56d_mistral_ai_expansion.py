"""mistral AI expansion: relevance scoring, dedupe embeddings, usage tracking, feedback loop

Revision ID: 51cd451dd56d
Revises: e596adeb683e
Create Date: 2026-07-05 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = '51cd451dd56d'
down_revision: Union[str, None] = 'e596adeb683e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- articles: semantic-dedupe support ---
    op.add_column('articles', sa.Column('embedding', postgresql.ARRAY(sa.Float()), nullable=True))
    op.add_column(
        'articles',
        sa.Column('duplicate_of_article_id', postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        'fk_articles_duplicate_of_article_id',
        'articles',
        'articles',
        ['duplicate_of_article_id'],
        ['id'],
        ondelete='SET NULL',
    )
    op.add_column('articles', sa.Column('skip_reason', sa.String(length=32), nullable=True))

    # --- signals: prioritization, structured extraction, multi-channel outreach, token usage ---
    op.alter_column('signals', 'outreach_snippet', new_column_name='outreach_snippet_email')
    op.add_column(
        'signals',
        sa.Column('outreach_snippet_linkedin', sa.Text(), nullable=False, server_default=''),
    )
    op.add_column(
        'signals',
        sa.Column('outreach_call_opener', sa.Text(), nullable=False, server_default=''),
    )
    op.add_column('signals', sa.Column('relevance_score', sa.Integer(), nullable=True))
    op.add_column('signals', sa.Column('signal_type', sa.Text(), nullable=True))
    op.add_column('signals', sa.Column('confidence', sa.Text(), nullable=True))
    op.add_column('signals', sa.Column('supporting_quote', sa.Text(), nullable=True))
    op.add_column('signals', sa.Column('entities', postgresql.JSON(), nullable=True))
    op.add_column('signals', sa.Column('prompt_tokens', sa.Integer(), nullable=True))
    op.add_column('signals', sa.Column('completion_tokens', sa.Integer(), nullable=True))
    op.add_column('signals', sa.Column('total_tokens', sa.Integer(), nullable=True))

    # Drop the server defaults now that existing rows are backfilled; the app always
    # supplies these explicitly going forward.
    op.alter_column('signals', 'outreach_snippet_linkedin', server_default=None)
    op.alter_column('signals', 'outreach_call_opener', server_default=None)

    # --- workspace_settings: rule-based feedback note injected into future prompts ---
    op.add_column(
        'workspace_settings',
        sa.Column('ai_feedback_note', sa.Text(), nullable=False, server_default=''),
    )
    op.alter_column('workspace_settings', 'ai_feedback_note', server_default=None)

    # --- ai_usage_logs: per-call token/cost tracking ---
    op.create_table(
        'ai_usage_logs',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('call_type', sa.String(length=32), nullable=False),
        sa.Column('model', sa.String(length=64), nullable=False),
        sa.Column('prompt_tokens', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('completion_tokens', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('total_tokens', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('target_company_id', postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        'fk_ai_usage_logs_target_company_id',
        'ai_usage_logs',
        'target_companies',
        ['target_company_id'],
        ['id'],
        ondelete='SET NULL',
    )
    op.create_index(
        'ix_ai_usage_logs_created_at', 'ai_usage_logs', ['created_at']
    )


def downgrade() -> None:
    op.drop_index('ix_ai_usage_logs_created_at', table_name='ai_usage_logs')
    op.drop_table('ai_usage_logs')

    op.drop_column('workspace_settings', 'ai_feedback_note')

    op.drop_column('signals', 'total_tokens')
    op.drop_column('signals', 'completion_tokens')
    op.drop_column('signals', 'prompt_tokens')
    op.drop_column('signals', 'entities')
    op.drop_column('signals', 'supporting_quote')
    op.drop_column('signals', 'confidence')
    op.drop_column('signals', 'signal_type')
    op.drop_column('signals', 'relevance_score')
    op.drop_column('signals', 'outreach_call_opener')
    op.drop_column('signals', 'outreach_snippet_linkedin')
    op.alter_column('signals', 'outreach_snippet_email', new_column_name='outreach_snippet')

    op.drop_column('articles', 'skip_reason')
    op.drop_constraint('fk_articles_duplicate_of_article_id', 'articles', type_='foreignkey')
    op.drop_column('articles', 'duplicate_of_article_id')
    op.drop_column('articles', 'embedding')
