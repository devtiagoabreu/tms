"""TMS 8.0: cadastros de grupos de teares e operadores expandido.

Revision ID: m4n5o6p7q8r9
Revises: z3a4b5c6d7e8
Create Date: 2026-11-12 13:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "m4n5o6p7q8r9"
down_revision = "z3a4b5c6d7e8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ---- Tabela machine_groups ----
    op.create_table(
        "machine_groups",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False, index=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "shift_turn_id",
            sa.Integer(),
            sa.ForeignKey("shift_turns.id"),
            nullable=True,
            index=True,
        ),
        sa.Column("active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # ---- Tabela machine_group_members ----
    op.create_table(
        "machine_group_members",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "group_id",
            sa.Integer(),
            sa.ForeignKey("machine_groups.id"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "machine_id",
            sa.Integer(),
            sa.ForeignKey("machines.id"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "group_id", "machine_id", name="uq_machine_group_member"
        ),
    )

    # ---- Colunas novas em operators ----
    with op.batch_alter_table("operators") as batch_op:
        batch_op.add_column(
            sa.Column("role", sa.String(length=32), nullable=True, server_default="tecelao")
        )
        batch_op.add_column(
            sa.Column(
                "group_id",
                sa.Integer(),
                sa.ForeignKey("machine_groups.id"),
                nullable=True,
                index=True,
            )
        )
        batch_op.add_column(
            sa.Column("active", sa.Boolean(), nullable=False, server_default="true")
        )
        batch_op.add_column(
            sa.Column(
                "created_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.text("now()"),
            )
        )
        batch_op.add_column(
            sa.Column(
                "updated_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.text("now()"),
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("operators") as batch_op:
        batch_op.drop_column("updated_at")
        batch_op.drop_column("created_at")
        batch_op.drop_column("active")
        batch_op.drop_column("group_id")
        batch_op.drop_column("role")

    op.drop_table("machine_group_members")
    op.drop_table("machine_groups")
