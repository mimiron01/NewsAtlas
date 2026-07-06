"""role-based access: users.role + company_follows

Revision ID: b582dced558e
Revises: e596adeb683e
Create Date: 2026-07-06 09:00:00.000000

"""
import uuid
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b582dced558e'
down_revision: Union[str, None] = 'e596adeb683e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()

    role_enum = sa.Enum('admin', 'user', name='user_role')
    role_enum.create(bind, checkfirst=True)
    op.add_column(
        'users',
        sa.Column('role', role_enum, nullable=False, server_default='user'),
    )

    op.create_table(
        'company_follows',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('target_company_id', sa.UUID(), nullable=False),
        sa.Column('is_muted', sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column('assigned_by', sa.UUID(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['target_company_id'], ['target_companies.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['assigned_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'target_company_id', name='uq_company_follows_user_company'),
    )

    # Bootstrap admin: the earliest-created existing account becomes admin. If the
    # table is empty this is a no-op — the next signup is promoted per api/auth.py.
    bind.execute(sa.text(
        "UPDATE users SET role = 'admin' "
        "WHERE id = (SELECT id FROM users ORDER BY created_at ASC, id ASC LIMIT 1)"
    ))

    # Full cross-join backfill: preserves today's "everyone sees everything" behavior
    # at migration time instead of silently hiding companies users could see before.
    users = bind.execute(sa.text("SELECT id FROM users")).fetchall()
    companies = bind.execute(sa.text("SELECT id FROM target_companies")).fetchall()
    if users and companies:
        company_follows_table = sa.table(
            'company_follows',
            sa.column('id', sa.UUID()),
            sa.column('user_id', sa.UUID()),
            sa.column('target_company_id', sa.UUID()),
        )
        rows = [
            {"id": uuid.uuid4(), "user_id": user.id, "target_company_id": company.id}
            for user in users
            for company in companies
        ]
        bind.execute(sa.insert(company_follows_table), rows)


def downgrade() -> None:
    op.drop_table('company_follows')
    op.drop_column('users', 'role')
    sa.Enum(name='user_role').drop(op.get_bind(), checkfirst=True)
