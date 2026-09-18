"""add ip_ranges and style columns (Fase 4 - configuração)

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-09-17 22:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e5f6a7b8c9d0'
down_revision: Union[str, Sequence[str], None] = 'd4e5f6a7b8c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('styles', sa.Column('density', sa.String(length=32), nullable=True))
    op.add_column('styles', sa.Column('doff_len', sa.Integer(), nullable=True))

    op.create_table(
        'ip_ranges',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('a', sa.Integer(), nullable=False),
        sa.Column('b', sa.Integer(), nullable=False),
        sa.Column('c', sa.Integer(), nullable=False),
        sa.Column('start', sa.Integer(), nullable=False),
        sa.Column('end', sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('ip_ranges')
    op.drop_column('styles', 'doff_len')
    op.drop_column('styles', 'density')
