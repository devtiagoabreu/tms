"""Configuração do sistema (chave/valor com categoria) — inspirado no pdmtextil.

Armazena preferências de instalação: dados da empresa, tema, integrações, etc.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from tms.db.base import Base


class SystemConfig(Base):
    """Parâmetro de configuração do sistema."""

    __tablename__ = "system_config"

    id: Mapped[int] = mapped_column(primary_key=True)
    categoria: Mapped[str] = mapped_column(String(32), nullable=False, index=True)  # empresa|tema|integracao|geral
    chave: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    valor: Mapped[str | None] = mapped_column(Text, nullable=True)
    tipo: Mapped[str] = mapped_column(String(16), default="text", nullable=False)  # text|number|boolean|json
    descricao: Mapped[str | None] = mapped_column(String(200), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    __table_args__ = (
        UniqueConstraint("categoria", "chave", name="uq_system_config_categoria_chave"),
    )
