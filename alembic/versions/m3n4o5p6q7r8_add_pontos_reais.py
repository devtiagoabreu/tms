"""add pontos_reais to daily_loom_data

Revision ID: m3n4o5p6q7r8
Revises: f84fa169ab6b
Create Date: 2026-11-10 21:00:00.000000

Adiciona coluna pontos_reais (Float) a daily_loom_data.
pontos_reais = picks * 1000 / 100 = picks * 10
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'm3n4o5p6q7r8'
down_revision: Union[str, Sequence[str], None] = 'f84fa169ab6b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    existing = _tables()
    if 'daily_loom_data' in existing:
        cols = {c['name'] for c in sa.inspect(op.get_bind()).get_columns('daily_loom_data')}
        if 'pontos_reais' not in cols:
            op.add_column(
                'daily_loom_data',
                sa.Column('pontos_reais', sa.Float(), nullable=True),
            )


def downgrade() -> None:
    existing = _tables()
    if 'daily_loom_data' in existing:
        cols = {c['name'] for c in sa.inspect(op.get_bind()).get_columns('daily_loom_data')}
        if 'pontos_reais' in cols:
            op.drop_column('daily_loom_data', 'pontos_reais')
