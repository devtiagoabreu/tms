"""add shift_id to daily_raw

Revision ID: b1d2e3f4a5c6
Revises: 9a6037a68657
Create Date: 2026-09-17 18:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b1d2e3f4a5c6'
down_revision: Union[str, Sequence[str], None] = '9a6037a68657'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('daily_raw', sa.Column('shift_id', sa.String(length=32), nullable=True))
    op.create_index(op.f('ix_daily_raw_shift_id'), 'daily_raw', ['shift_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_daily_raw_shift_id'), table_name='daily_raw')
    op.drop_column('daily_raw', 'shift_id')
