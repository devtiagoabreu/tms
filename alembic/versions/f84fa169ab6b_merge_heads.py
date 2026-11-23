"""merge heads

Revision ID: f84fa169ab6b
Revises: a1b2c3d4e5f6, g7h8i9j0k1l2
Create Date: 2026-11-10 17:53:43.519311

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f84fa169ab6b'
down_revision: Union[str, Sequence[str], None] = ('a1b2c3d4e5f6', 'g7h8i9j0k1l2')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
