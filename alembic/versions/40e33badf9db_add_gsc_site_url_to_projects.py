"""\add_gsc_site_url_to_projects\

Revision ID: 40e33badf9db
Revises: 12b6d19acc7a
Create Date: 2025-05-11 18:16:16.490606

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '40e33badf9db'
down_revision: Union[str, None] = '12b6d19acc7a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('projects', sa.Column('gsc_site_url', sa.String(), nullable=True))
    op.create_index(op.f('ix_projects_gsc_site_url'), 'projects', ['gsc_site_url'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_projects_gsc_site_url'), table_name='projects')
    op.drop_column('projects', 'gsc_site_url')
