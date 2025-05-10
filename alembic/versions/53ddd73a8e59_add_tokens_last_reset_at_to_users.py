"""add_tokens_last_reset_at_to_users

Revision ID: 53ddd73a8e59
Revises: 9986914632aa
Create Date: 2025-05-11 00:10:11.642286

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '53ddd73a8e59'
down_revision: Union[str, None] = '9986914632aa'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('users', sa.Column('tokens_last_reset_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('users', 'tokens_last_reset_at')
