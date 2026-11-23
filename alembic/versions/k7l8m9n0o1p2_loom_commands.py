"""TMS 8.0: tabela loom_commands para envio de dados aos teares.

Revision ID: k7l8m9n0o1p2
Revises: m4n5o6p7q8r9
Create Date: 2026-11-12 14:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "k7l8m9n0o1p2"
down_revision = "m4n5o6p7q8r9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "loom_commands",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "machine_id",
            sa.Integer(),
            sa.ForeignKey("machines.id"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "command_type",
            sa.String(length=32),
            nullable=False,
        ),
        sa.Column("payload", sa.Text(), nullable=True),
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("sent_at", sa.DateTime(), nullable=True),
        sa.Column("acknowledged_at", sa.DateTime(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("loom_commands")
