"""add picks and meters to daily loom data

Revision ID: a1b2c3d4e5f6
Revises: f6a7b8c9d0e1
Create Date: 2026-11-05 12:00:00.000000

Produção diária do tear: ``picks`` (pontos) e ``meters`` (metros), extraídos do
bloco ``PM_yN_p5_seisan`` do payload ``tms_get_monitor_data``.  A migração é
idempotente porque tabelas criadas com ``Base.metadata.create_all`` já podem
conter as colunas.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = 'f6a7b8c9d0e1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _columns(table: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    if table not in inspector.get_table_names():
        return set()
    return {column['name'] for column in inspector.get_columns(table)}


def upgrade() -> None:
    """Upgrade schema."""
    existing = _columns('daily_loom_data')
    if 'picks' not in existing:
        op.add_column('daily_loom_data', sa.Column('picks', sa.Float(), nullable=True))
    if 'meters' not in existing:
        op.add_column('daily_loom_data', sa.Column('meters', sa.Float(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    existing = _columns('daily_loom_data')
    if 'meters' in existing:
        op.drop_column('daily_loom_data', 'meters')
    if 'picks' in existing:
        op.drop_column('daily_loom_data', 'picks')
