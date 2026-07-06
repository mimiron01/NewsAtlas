"""merge mistral expansion and role-based access

Revision ID: 48a3154f0000
Revises: 51cd451dd56d, b582dced558e
Create Date: 2026-07-06 13:16:52.982128

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '48a3154f0000'
down_revision: Union[str, None] = ('51cd451dd56d', 'b582dced558e')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
