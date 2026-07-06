"""admin-editable Mistral integration settings on workspace_settings

Revision ID: ac9f253eecea
Revises: 48a3154f0000
Create Date: 2026-07-06 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'ac9f253eecea'
down_revision: Union[str, None] = '48a3154f0000'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'workspace_settings',
        sa.Column('mistral_api_key', sa.Text(), nullable=False, server_default=''),
    )
    op.add_column(
        'workspace_settings',
        sa.Column('mistral_model', sa.String(length=100), nullable=False, server_default='mistral-large-latest'),
    )
    op.add_column(
        'workspace_settings',
        sa.Column('mistral_triage_model', sa.String(length=100), nullable=False, server_default='mistral-small-latest'),
    )
    op.add_column(
        'workspace_settings',
        sa.Column('mistral_embed_model', sa.String(length=100), nullable=False, server_default='mistral-embed'),
    )
    op.add_column(
        'workspace_settings',
        sa.Column('mistral_triage_enabled', sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column(
        'workspace_settings',
        sa.Column(
            'mistral_dedupe_similarity_threshold', sa.Float(), nullable=False, server_default='0.9'
        ),
    )

    # Backfill any existing workspace_settings row with whatever these were previously
    # configured to via environment variables, so upgrading a live deployment doesn't
    # silently reset an operator's non-default MISTRAL_* choice back to the hardcoded
    # default the moment this migration runs. The API key is deliberately NOT backfilled
    # here: it stays sourced from the env var until an admin explicitly sets an override
    # in-app (see app/services/ai_client_config.py), so no secret is copied into the
    # database as a side effect of a schema migration (see
    # app/services/workspace_settings.py:resolve_mistral_api_key).
    from app.core.config import get_settings

    app_settings = get_settings()
    bind = op.get_bind()
    bind.execute(
        sa.text(
            "UPDATE workspace_settings SET "
            "mistral_model = :model, "
            "mistral_triage_model = :triage_model, "
            "mistral_embed_model = :embed_model, "
            "mistral_triage_enabled = :triage_enabled, "
            "mistral_dedupe_similarity_threshold = :dedupe_threshold"
        ),
        {
            "model": app_settings.mistral_model,
            "triage_model": app_settings.mistral_triage_model,
            "embed_model": app_settings.mistral_embed_model,
            "triage_enabled": app_settings.mistral_triage_enabled,
            "dedupe_threshold": app_settings.mistral_dedupe_similarity_threshold,
        },
    )

    op.alter_column('workspace_settings', 'mistral_api_key', server_default=None)
    op.alter_column('workspace_settings', 'mistral_model', server_default=None)
    op.alter_column('workspace_settings', 'mistral_triage_model', server_default=None)
    op.alter_column('workspace_settings', 'mistral_embed_model', server_default=None)
    op.alter_column('workspace_settings', 'mistral_triage_enabled', server_default=None)
    op.alter_column('workspace_settings', 'mistral_dedupe_similarity_threshold', server_default=None)


def downgrade() -> None:
    op.drop_column('workspace_settings', 'mistral_dedupe_similarity_threshold')
    op.drop_column('workspace_settings', 'mistral_triage_enabled')
    op.drop_column('workspace_settings', 'mistral_embed_model')
    op.drop_column('workspace_settings', 'mistral_triage_model')
    op.drop_column('workspace_settings', 'mistral_model')
    op.drop_column('workspace_settings', 'mistral_api_key')
