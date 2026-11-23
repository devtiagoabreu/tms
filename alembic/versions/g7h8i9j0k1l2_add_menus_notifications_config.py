"""add menus, notifications and system_config tables

Revision ID: g7h8i9j0k1l2
Revises: f6a7b8c9d0e1
Create Date: 2026-11-10 10:00:00.000000

Tabelas de navegacao, notificacao e configuracao do sistema (inspirado no pdmtextil).
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'g7h8i9j0k1l2'
down_revision: Union[str, Sequence[str], None] = 'f6a7b8c9d0e1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    """Upgrade schema."""
    existing = _tables()

    if 'menus' not in existing:
        op.create_table(
            'menus',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('title', sa.String(length=64), nullable=False),
            sa.Column('icon', sa.String(length=32), nullable=True),
            sa.Column('url', sa.String(length=255), nullable=True),
            sa.Column('ordem', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('role', sa.String(length=32), nullable=True),
            sa.Column('usuario_id', sa.Integer(), nullable=True),
            sa.Column('active', sa.Boolean(), nullable=False, server_default='1'),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(['usuario_id'], ['users.id']),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('title', 'usuario_id', name='uq_menu_title_usuario'),
        )
        op.create_index(op.f('ix_menus_usuario_id'), 'menus', ['usuario_id'])

    if 'menu_items' not in existing:
        op.create_table(
            'menu_items',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('menu_id', sa.Integer(), nullable=False),
            sa.Column('title', sa.String(length=64), nullable=False),
            sa.Column('url', sa.String(length=255), nullable=True),
            sa.Column('icon', sa.String(length=32), nullable=True),
            sa.Column('ordem', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('active', sa.Boolean(), nullable=False, server_default='1'),
            sa.ForeignKeyConstraint(['menu_id'], ['menus.id'], ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('id'),
        )
        op.create_index(op.f('ix_menu_items_menu_id'), 'menu_items', ['menu_id'])

    if 'notifications' not in existing:
        op.create_table(
            'notifications',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('tipo', sa.String(length=32), nullable=False),
            sa.Column('mensagem', sa.Text(), nullable=False),
            sa.Column('link', sa.String(length=255), nullable=True),
            sa.Column('usuario_id', sa.Integer(), nullable=False),
            sa.Column('lida', sa.Boolean(), nullable=False, server_default='0'),
            sa.Column('criada_em', sa.DateTime(), nullable=False),
            sa.Column('lida_em', sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(['usuario_id'], ['users.id']),
            sa.PrimaryKeyConstraint('id'),
        )
        op.create_index(
            op.f('ix_notifications_usuario_id'), 'notifications', ['usuario_id']
        )
        op.create_index(op.f('ix_notifications_tipo'), 'notifications', ['tipo'])
        op.create_index(op.f('ix_notifications_lida'), 'notifications', ['lida'])

    if 'notification_rules' not in existing:
        op.create_table(
            'notification_rules',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('tipo', sa.String(length=32), nullable=False),
            sa.Column('roles_json', sa.Text(), nullable=False),
            sa.Column('ativo', sa.Boolean(), nullable=False, server_default='1'),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('tipo', name='uq_notification_rules_tipo'),
        )

    if 'system_config' not in existing:
        op.create_table(
            'system_config',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('categoria', sa.String(length=32), nullable=False),
            sa.Column('chave', sa.String(length=64), nullable=False),
            sa.Column('valor', sa.Text(), nullable=True),
            sa.Column('tipo', sa.String(length=16), nullable=False, server_default='text'),
            sa.Column('descricao', sa.String(length=200), nullable=True),
            sa.Column('updated_at', sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint(
                'categoria', 'chave', name='uq_system_config_categoria_chave'
            ),
        )
        op.create_index(
            op.f('ix_system_config_categoria'), 'system_config', ['categoria']
        )


def downgrade() -> None:
    """Downgrade schema."""
    existing = _tables()
    if 'system_config' in existing:
        op.drop_index(op.f('ix_system_config_categoria'), table_name='system_config')
        op.drop_table('system_config')
    if 'notification_rules' in existing:
        op.drop_table('notification_rules')
    if 'notifications' in existing:
        op.drop_index(op.f('ix_notifications_lida'), table_name='notifications')
        op.drop_index(op.f('ix_notifications_tipo'), table_name='notifications')
        op.drop_index(op.f('ix_notifications_usuario_id'), table_name='notifications')
        op.drop_table('notifications')
    if 'menu_items' in existing:
        op.drop_index(op.f('ix_menu_items_menu_id'), table_name='menu_items')
        op.drop_table('menu_items')
    if 'menus' in existing:
        op.drop_index(op.f('ix_menus_usuario_id'), table_name='menus')
        op.drop_table('menus')
