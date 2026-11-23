"""Cadastros de grupos de teares e operadores (TMS 8.0).

- MachineGroup: grupo de teares (ex: Setor A, Setor B, LWT, etc.)
- MachineGroupMember: vinculo N:N entre grupo e tear
- Operator expandido: cargo (tecelão, contra-mestre) e grupo vinculado
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from tms.db.base import Base


class MachineGroup(Base):
    """Grupo de teares (ex: Setor A, Setor B, LWT, JAT)."""

    __tablename__ = "machine_groups"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    shift_turn_id: Mapped[int | None] = mapped_column(
        ForeignKey("shift_turns.id"), nullable=True, index=True
    )
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    shift_turn = relationship("ShiftTurn")
    members = relationship(
        "MachineGroupMember",
        back_populates="group",
        cascade="all, delete-orphan",
    )


class MachineGroupMember(Base):
    """Vinculo de um tear a um grupo."""

    __tablename__ = "machine_group_members"
    __table_args__ = (
        UniqueConstraint("group_id", "machine_id", name="uq_machine_group_member"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    group_id: Mapped[int] = mapped_column(
        ForeignKey("machine_groups.id"), index=True, nullable=False
    )
    machine_id: Mapped[int] = mapped_column(
        ForeignKey("machines.id"), index=True, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )

    group = relationship("MachineGroup", back_populates="members")
    machine = relationship("Machine")
