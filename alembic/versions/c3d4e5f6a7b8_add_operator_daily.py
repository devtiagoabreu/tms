"""add operator_daily table

Revision ID: c3d4e5f6a7b8
Revises: b1d2e3f4a5c6
Create Date: 2026-09-17 19:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, Sequence[str], None] = 'b1d2e3f4a5c6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'operator_daily',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('machine_id', sa.Integer(), nullable=False),
        sa.Column('operator_id', sa.Integer(), nullable=False),
        sa.Column('day', sa.String(length=10), nullable=False),
        sa.Column('start_time', sa.DateTime(), nullable=True),
        sa.Column('seisan', sa.JSON(), nullable=True),
        sa.Column('run_tm', sa.Integer(), nullable=True),
        sa.Column('stop_ttm', sa.Integer(), nullable=True),
        sa.Column('s_ct', sa.JSON(), nullable=True),
        sa.Column('s_tm', sa.JSON(), nullable=True),
        sa.Column('raw_line', sa.Text(), nullable=True),
        sa.Column('collected_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['machine_id'], ['machines.id']),
        sa.ForeignKeyConstraint(['operator_id'], ['operators.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_operator_daily_machine_id'), 'operator_daily', ['machine_id'])
    op.create_index(op.f('ix_operator_daily_operator_id'), 'operator_daily', ['operator_id'])
    op.create_index(op.f('ix_operator_daily_day'), 'operator_daily', ['day'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_operator_daily_day'), table_name='operator_daily')
    op.drop_index(op.f('ix_operator_daily_operator_id'), table_name='operator_daily')
    op.drop_index(op.f('ix_operator_daily_machine_id'), table_name='operator_daily')
    op.drop_table('operator_daily')
