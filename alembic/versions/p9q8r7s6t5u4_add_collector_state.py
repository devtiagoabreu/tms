"""Add collector_state table for the continuous live collector.

Revision ID: p9q8r7s6t5u4
Revises: n5o6p7q8r9s0_add_double_and_metros_reais
Create Date: 2026-11-12 10:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "p9q8r7s6t5u4"
down_revision = "n5o6p7q8r9s0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "collector_state",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("interval_s", sa.Integer(), nullable=False, server_default="60"),
        sa.Column("last_collected_at", sa.DateTime(), nullable=True),
        sa.Column("next_collect_at", sa.DateTime(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.execute(
        "INSERT INTO collector_state (id, enabled, interval_s, updated_at) "
        "VALUES (1, true, 60, now())"
    )


def downgrade() -> None:
    op.drop_table("collector_state")
