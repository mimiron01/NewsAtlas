"""encrypt mistral_api_key/newsdata_api_key at rest in place

Revision ID: fe46f8cfc9d5
Revises: 7c4230826d8b
Create Date: 2026-07-21 00:20:00.000000

Data-only migration: no schema change (both columns were already Text). Re-encrypts
whatever plaintext value is currently stored using APP_SECRET_KEY, which must already
be set in the environment this migration runs in (see app/core/config.py's
assert_secure_for_production and app/core/crypto.py) — this is a required env var going
forward, the same hard-fail-in-production convention as JWT_SECRET.

Idempotent: a value that already decrypts successfully under the current
APP_SECRET_KEY is left untouched, so re-running this migration (or running it after a
downgrade/upgrade cycle) never double-encrypts.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from app.core.crypto import CryptoError, decrypt_secret, encrypt_secret

revision: str = 'fe46f8cfc9d5'
down_revision: Union[str, None] = '7c4230826d8b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    rows = bind.execute(
        sa.text('SELECT id, mistral_api_key, newsdata_api_key FROM workspace_settings')
    ).fetchall()

    for row in rows:
        updates = {}
        for column, value in (("mistral_api_key", row.mistral_api_key), ("newsdata_api_key", row.newsdata_api_key)):
            if not value:
                continue
            try:
                decrypt_secret(value)
                continue  # already a valid ciphertext under the current key — leave it
            except CryptoError:
                pass
            updates[column] = encrypt_secret(value)

        if updates:
            set_clause = ", ".join(f"{column} = :{column}" for column in updates)
            bind.execute(
                sa.text(f"UPDATE workspace_settings SET {set_clause} WHERE id = :id"),
                {**updates, "id": row.id},
            )


def downgrade() -> None:
    # Decrypting back to plaintext on downgrade would defeat the point of a security
    # fix and isn't something a rollback should ever silently do — if a downgrade is
    # genuinely needed, restore the pre-migration values from a backup instead.
    pass
