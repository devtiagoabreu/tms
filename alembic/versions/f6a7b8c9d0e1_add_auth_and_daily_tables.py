"""add users and daily collection tables

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-10-28 10:00:00.000000

As tabelas ``users`` e do dashboard diário podem já existir em bancos criados
com ``Base.metadata.create_all``; por isso a migração só cria o que faltar.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f6a7b8c9d0e1'
down_revision: Union[str, Sequence[str], None] = 'e5f6a7b8c9d0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    """Upgrade schema."""
    existing = _tables()

    if 'users' not in existing:
        user_role = sa.Enum('admin', 'operador', 'visualizador', name='userrole')
        op.create_table(
            'users',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('email', sa.String(length=255), nullable=False),
            sa.Column('username', sa.String(length=64), nullable=True),
            sa.Column('full_name', sa.String(length=128), nullable=True),
            sa.Column('password_hash', sa.String(length=255), nullable=False),
            sa.Column('role', user_role, nullable=False),
            sa.Column('is_active', sa.Boolean(), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.Column('last_login_at', sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint('id'),
        )
        op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=True)
        op.create_index(op.f('ix_users_username'), 'users', ['username'], unique=True)

    if 'daily_collection_runs' not in existing:
        op.create_table(
            'daily_collection_runs',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('collection_date', sa.Date(), nullable=False),
            sa.Column('status', sa.String(length=16), nullable=False),
            sa.Column('started_at', sa.DateTime(), nullable=True),
            sa.Column('finished_at', sa.DateTime(), nullable=True),
            sa.Column('total_machines', sa.Integer(), nullable=False),
            sa.Column('success_count', sa.Integer(), nullable=False),
            sa.Column('failed_count', sa.Integer(), nullable=False),
            sa.Column('retry_count', sa.Integer(), nullable=False),
            sa.Column('notes', sa.Text(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('collection_date', name='uq_daily_collection_run_date'),
        )
        op.create_index(
            op.f('ix_daily_collection_runs_collection_date'),
            'daily_collection_runs',
            ['collection_date'],
            unique=True,
        )

    if 'daily_collection_items' not in existing:
        op.create_table(
            'daily_collection_items',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('run_id', sa.Integer(), nullable=False),
            sa.Column('machine_id', sa.Integer(), nullable=False),
            sa.Column('mac_name', sa.String(length=32), nullable=False),
            sa.Column('mac_type', sa.String(length=8), nullable=False),
            sa.Column('ip_addr', sa.String(length=45), nullable=True),
            sa.Column('status', sa.String(length=16), nullable=False),
            sa.Column('attempts', sa.Integer(), nullable=False),
            sa.Column('error_reason', sa.Text(), nullable=True),
            sa.Column('collected_at', sa.DateTime(), nullable=True),
            sa.Column('data_json', sa.JSON(), nullable=True),
            sa.Column('in_retry_queue', sa.Boolean(), nullable=False),
            sa.Column('last_retry_at', sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(['machine_id'], ['machines.id']),
            sa.ForeignKeyConstraint(['run_id'], ['daily_collection_runs.id']),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint(
                'run_id', 'machine_id', name='uq_daily_collection_item_run_machine'
            ),
        )
        op.create_index(
            op.f('ix_daily_collection_items_run_id'), 'daily_collection_items', ['run_id']
        )
        op.create_index(
            op.f('ix_daily_collection_items_machine_id'), 'daily_collection_items', ['machine_id']
        )
        op.create_index(
            op.f('ix_daily_collection_items_mac_name'), 'daily_collection_items', ['mac_name']
        )

    if 'daily_loom_data' not in existing:
        op.create_table(
            'daily_loom_data',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('collection_date', sa.Date(), nullable=False),
            sa.Column('machine_id', sa.Integer(), nullable=False),
            sa.Column('mac_name', sa.String(length=32), nullable=False),
            sa.Column('source', sa.String(length=16), nullable=False),
            sa.Column('shift_id', sa.String(length=32), nullable=True),
            sa.Column('style', sa.String(length=64), nullable=True),
            sa.Column('beam', sa.String(length=32), nullable=True),
            sa.Column('production', sa.Float(), nullable=True),
            sa.Column('efficiency', sa.Float(), nullable=True),
            sa.Column('rpm', sa.Float(), nullable=True),
            sa.Column('run_time_min', sa.Float(), nullable=True),
            sa.Column('stop_time_min', sa.Float(), nullable=True),
            sa.Column('total_stop_ct', sa.Integer(), nullable=True),
            sa.Column('total_stop_tm_min', sa.Float(), nullable=True),
            sa.Column('trama_stops', sa.Integer(), nullable=True),
            sa.Column('trama_stops_min', sa.Float(), nullable=True),
            sa.Column('urdume_stops', sa.Integer(), nullable=True),
            sa.Column('urdume_stops_min', sa.Float(), nullable=True),
            sa.Column('outros_stops', sa.Integer(), nullable=True),
            sa.Column('outros_stops_min', sa.Float(), nullable=True),
            sa.Column('raw_data', sa.JSON(), nullable=True),
            sa.Column('collected_at', sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(['machine_id'], ['machines.id']),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint(
                'collection_date', 'machine_id', name='uq_daily_loom_data_date_machine'
            ),
        )
        op.create_index(
            op.f('ix_daily_loom_data_collection_date'), 'daily_loom_data', ['collection_date']
        )
        op.create_index(
            op.f('ix_daily_loom_data_machine_id'), 'daily_loom_data', ['machine_id']
        )
        op.create_index(op.f('ix_daily_loom_data_mac_name'), 'daily_loom_data', ['mac_name'])
        op.create_index(op.f('ix_daily_loom_data_shift_id'), 'daily_loom_data', ['shift_id'])


def downgrade() -> None:
    """Downgrade schema."""
    existing = _tables()
    if 'daily_loom_data' in existing:
        for name in (
            'ix_daily_loom_data_shift_id',
            'ix_daily_loom_data_mac_name',
            'ix_daily_loom_data_machine_id',
            'ix_daily_loom_data_collection_date',
        ):
            op.drop_index(op.f(name), table_name='daily_loom_data')
        op.drop_table('daily_loom_data')
    if 'daily_collection_items' in existing:
        for name in (
            'ix_daily_collection_items_mac_name',
            'ix_daily_collection_items_machine_id',
            'ix_daily_collection_items_run_id',
        ):
            op.drop_index(op.f(name), table_name='daily_collection_items')
        op.drop_table('daily_collection_items')
    if 'daily_collection_runs' in existing:
        op.drop_index(
            op.f('ix_daily_collection_runs_collection_date'),
            table_name='daily_collection_runs',
        )
        op.drop_table('daily_collection_runs')
    if 'users' in existing:
        op.drop_index(op.f('ix_users_username'), table_name='users')
        op.drop_index(op.f('ix_users_email'), table_name='users')
        op.drop_table('users')
