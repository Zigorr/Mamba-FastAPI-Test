"""add_user_token_and_verification_fields

Revision ID: bb25027e7247
Revises: 6138f0126969
Create Date: 2025-05-10 01:17:08.821038

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'bb25027e7247'
down_revision: Union[str, None] = '6138f0126969'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
