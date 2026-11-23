"""TMS 8.0: tabelas de roles e permissões granulares.

Revision ID: s9t8u7v6w5x4
Revises: k7l8m9n0o1p2
Create Date: 2026-11-13 09:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "s9t8u7v6w5x4"
down_revision = "k7l8m9n0o1p2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "permissions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("chave", sa.String(length=64), nullable=False, index=True),
        sa.Column("descricao", sa.String(length=200), nullable=True),
        sa.Column("modulo", sa.String(length=32), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("chave", name="uq_permissions_chave"),
    )

    op.create_table(
        "role_permissions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False, index=True),
        sa.Column(
            "permission_id",
            sa.Integer(),
            sa.ForeignKey("permissions.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("role", "permission_id", name="uq_role_permission"),
    )

    # Permissões padrão (inserir com valores embutidos)
    op.execute(
        "INSERT INTO permissions (chave, descricao, modulo, active, created_at) VALUES "
        "('teares.ver', 'Ver teares', 'teares', true, now()), "
        "('teares.editar', 'Editar teares', 'teares', true, now()), "
        "('teares.comandos', 'Enviar comandos para teares', 'teares', true, now()), "
        "('coletar.executar', 'Executar coleta manual', 'coletar', true, now()), "
        "('menus.configurar', 'Configurar menus e submenus', 'menus', true, now()), "
        "('menus.ver', 'Ver menus', 'menus', true, now()), "
        "('cadastros.ver', 'Ver cadastros (grupos, operadores)', 'cadastros', true, now()), "
        "('cadastros.editar', 'Editar cadastros', 'cadastros', true, now()), "
        "('relatorios.ver', 'Ver relatórios', 'relatorios', true, now()), "
        "('monitor.ver', 'Ver monitor ao vivo', 'monitor', true, now()), "
        "('admin.usuarios', 'Gerenciar usuários e roles', 'admin', true, now())"
    )

    # Role admin tem todas as permissões
    op.execute(
        "INSERT INTO role_permissions (role, permission_id, active, created_at) "
        "SELECT 'admin', id, true, now() FROM permissions"
    )

    # Role operador tem permissões de leitura e coleta
    op.execute(
        "INSERT INTO role_permissions (role, permission_id, active, created_at) "
        "SELECT 'operador', id, true, now() FROM permissions WHERE chave IN "
        "('teares.ver', 'coletar.executar', 'menus.ver', 'cadastros.ver', 'relatorios.ver', 'monitor.ver')"
    )

    # Role visualizador tem apenas leitura
    op.execute(
        "INSERT INTO role_permissions (role, permission_id, active, created_at) "
        "SELECT 'visualizador', id, true, now() FROM permissions WHERE chave IN "
        "('teares.ver', 'menus.ver', 'cadastros.ver', 'relatorios.ver', 'monitor.ver')"
    )


def downgrade() -> None:
    op.drop_table("role_permissions")
    op.drop_table("permissions")
