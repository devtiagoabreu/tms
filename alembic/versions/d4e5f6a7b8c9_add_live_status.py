"""add live_status table

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-09-17 21:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, Sequence[str], None] = 'c3d4e5f6a7b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'live_status',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('machine_id', sa.Integer(), nullable=False),
        sa.Column('collected_at', sa.DateTime(), nullable=False),
        sa.Column('mac_type', sa.String(length=8), nullable=False),
        sa.Column('state', sa.String(length=16), nullable=False),
        sa.Column('status', sa.String(length=24), nullable=False),
        sa.Column('error', sa.Integer(), nullable=True),
        sa.Column('complete', sa.Boolean(), nullable=False),
        sa.Column('duration', sa.Float(), nullable=True),
        sa.Column('rpm', sa.Float(), nullable=True),
        sa.Column('efficiency', sa.Float(), nullable=True),
        sa.Column('efficiency_24h', sa.Float(), nullable=True),
        sa.Column('bits', sa.JSON(), nullable=True),
        sa.Column('data', sa.JSON(), nullable=True),
        sa.Column('setup', sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(['machine_id'], ['machines.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_live_status_machine_id'), 'live_status', ['machine_id'])
    op.create_index(op.f('ix_live_status_collected_at'), 'live_status', ['collected_at'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_live_status_collected_at'), table_name='live_status')
    op.drop_index(op.f('ix_live_status_machine_id'), table_name='live_status')
    op.drop_table('live_status')
