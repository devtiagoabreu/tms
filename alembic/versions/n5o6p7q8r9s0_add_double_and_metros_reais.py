"""add is_double to machines and metros_reais to daily_loom_data

Revision ID: n5o6p7q8r9s0
Revises: m3n4o5p6q7r8
Create Date: 2026-11-10 22:00:00.000000

Adiciona:
- coluna is_double (Boolean) em machines, marcando teares duplos
- coluna metros_reais (Float) em daily_loom_data
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'n5o6p7q8r9s0'
down_revision: Union[str, Sequence[str], None] = 'm3n4o5p6q7r8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    existing = _tables()
    if 'machines' in existing:
        cols = {c['name'] for c in sa.inspect(op.get_bind()).get_columns('machines')}
        if 'is_double' not in cols:
            op.add_column(
                'machines',
                sa.Column('is_double', sa.Boolean(), nullable=False, server_default='0'),
            )
    if 'daily_loom_data' in existing:
        cols = {c['name'] for c in sa.inspect(op.get_bind()).get_columns('daily_loom_data')}
        if 'metros_reais' not in cols:
            op.add_column(
                'daily_loom_data',
                sa.Column('metros_reais', sa.Float(), nullable=True),
            )


def downgrade() -> None:
    existing = _tables()
    if 'daily_loom_data' in existing:
        cols = {c['name'] for c in sa.inspect(op.get_bind()).get_columns('daily_loom_data')}
        if 'metros_reais' in cols:
            op.drop_column('daily_loom_data', 'metros_reais')
    if 'machines' in existing:
        cols = {c['name'] for c in sa.inspect(op.get_bind()).get_columns('machines')}
        if 'is_double' in cols:
            op.drop_column('machines', 'is_double')
