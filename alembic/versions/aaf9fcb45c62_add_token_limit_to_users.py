"""add_token_limit_to_users

Revision ID: aaf9fcb45c62
Revises: 9736e90ad005
Create Date: 2025-05-10 23:38:29.578385

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'aaf9fcb45c62'
down_revision: Union[str, None] = '9736e90ad005'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('users', sa.Column('token_limit', sa.Integer(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('users', 'token_limit')
