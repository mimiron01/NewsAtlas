"""ingestion runs: progress tracking and history log

Revision ID: f2230b463357
Revises: f1a2b3c4d5e6
Create Date: 2026-07-07 15:23:49.363587

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f2230b463357'
down_revision: Union[str, None] = 'f1a2b3c4d5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'ingestion_runs',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False, server_default='running'),
        sa.Column('trigger', sa.String(length=16), nullable=False),
        sa.Column('triggered_by_user_id', sa.UUID(), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('companies_total', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('companies_processed', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('current_step', sa.String(length=16), nullable=True),
        sa.Column('current_company_name', sa.String(length=255), nullable=True),
        sa.Column('articles_total_this_company', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('articles_processed_this_company', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('articles_fetched', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('articles_new', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('signals_created', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('duplicates_skipped', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('triaged_out', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('by_source', sa.JSON(), nullable=False, server_default='{}'),
        sa.Column('rate_limited', sa.JSON(), nullable=False, server_default='{}'),
        sa.Column('errors', sa.JSON(), nullable=False, server_default='[]'),
        sa.Column('fatal_error', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['triggered_by_user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_ingestion_runs_started_at', 'ingestion_runs', ['started_at'], unique=False
    )


def downgrade() -> None:
    op.drop_index('ix_ingestion_runs_started_at', table_name='ingestion_runs')
    op.drop_table('ingestion_runs')
