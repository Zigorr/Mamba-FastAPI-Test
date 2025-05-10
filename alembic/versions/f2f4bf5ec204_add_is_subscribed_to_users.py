"""add_is_subscribed_to_users

Revision ID: f2f4bf5ec204
Revises: aaf9fcb45c62
Create Date: 2025-05-10 23:57:11.972453

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f2f4bf5ec204'
down_revision: Union[str, None] = 'aaf9fcb45c62'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('users', sa.Column('is_subscribed', sa.Boolean(), nullable=False, server_default=sa.text('false')))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('users', 'is_subscribed')
