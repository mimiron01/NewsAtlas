"""security hardening: token revocation and manual trigger cooldown

Revision ID: e596adeb683e
Revises: 79007b171d44
Create Date: 2026-07-03 13:43:16.320234

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e596adeb683e'
down_revision: Union[str, None] = '79007b171d44'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'users',
        sa.Column('token_version', sa.Integer(), nullable=False, server_default='0'),
    )
    op.add_column('workspace_settings', sa.Column('last_manual_ingestion_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('workspace_settings', sa.Column('last_manual_digest_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('workspace_settings', 'last_manual_digest_at')
    op.drop_column('workspace_settings', 'last_manual_ingestion_at')
    op.drop_column('users', 'token_version')
