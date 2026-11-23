"""Add shift_turn_id FK to daily_loom_data for per-turn efficiency.

Revision ID: z3a4b5c6d7e8
Revises: t7u8v9w0x1y2_add_shift_turns
Create Date: 2026-11-12 12:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "z3a4b5c6d7e8"
down_revision = "t7u8v9w0x1y2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("daily_loom_data") as batch_op:
        batch_op.add_column(
            sa.Column(
                "shift_turn_id",
                sa.Integer(),
                sa.ForeignKey("shift_turns.id"),
                nullable=True,
                index=True,
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("daily_loom_data") as batch_op:
        batch_op.drop_column("shift_turn_id")
