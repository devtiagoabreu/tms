"""Fila de comandos para envio aos teares (TMS 8.0).

Permite enviar dados/configuracoes para os teares, como:
- artigo/estilo atual
- turno vinculado
- comandos de controle (reiniciar contagem, ajustar relogio, etc.)
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
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from tms.db.base import Base


class LoomCommand(Base):
    """Comando enviado (ou a enviar) para um tear."""

    __tablename__ = "loom_commands"

    id: Mapped[int] = mapped_column(primary_key=True)
    machine_id: Mapped[int] = mapped_column(
        ForeignKey("machines.id"), index=True, nullable=False
    )
    command_type: Mapped[str] = mapped_column(
        String(32), nullable=False
    )  # set_style | set_shift | reset_counter | set_clock | custom
    payload: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON ou texto
    status: Mapped[str] = mapped_column(
        String(16), default="pending"
    )  # pending | sent | error | acknowledged
    sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )

    machine = relationship("Machine")
