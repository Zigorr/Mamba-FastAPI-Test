"""add_tokens_last_reset_at_to_users

Revision ID: 9986914632aa
Revises: f2f4bf5ec204
Create Date: 2025-05-11 00:09:29.806706

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9986914632aa'
down_revision: Union[str, None] = 'f2f4bf5ec204'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
