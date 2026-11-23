"""Add shift_turns table for detailed shift registration.

Revision ID: t7u8v9w0x1y2
Revises: p9q8r7s6t5u4_add_collector_state
Create Date: 2026-11-12 11:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "t7u8v9w0x1y2"
down_revision = "p9q8r7s6t5u4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "shift_turns",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=16), nullable=False),
        sa.Column("start_time", sa.String(length=5), nullable=False),
        sa.Column("end_time", sa.String(length=5), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column(
            "days_mask", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "wraps_midnight",
            sa.Boolean(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "sort_order", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_shift_turns_name"), "shift_turns", ["name"], unique=True
    )

    # Dados de exemplo padrao (desligados, para o administrador configurar)
    op.execute(
        "INSERT INTO shift_turns (name, start_time, end_time, active, days_mask, wraps_midnight, sort_order) "
        "VALUES ('A', '05:00', '14:00', true, 62, false, 1)"
    )
    op.execute(
        "INSERT INTO shift_turns (name, start_time, end_time, active, days_mask, wraps_midnight, sort_order) "
        "VALUES ('B', '14:00', '23:35', true, 62, false, 2)"
    )
    op.execute(
        "INSERT INTO shift_turns (name, start_time, end_time, active, days_mask, wraps_midnight, sort_order) "
        "VALUES ('C', '23:35', '05:00', false, 62, true, 3)"
    )


def downgrade() -> None:
    op.drop_table("shift_turns")
