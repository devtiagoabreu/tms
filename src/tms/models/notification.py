"""Modelos de notificações — inspirado no pdmtextil.

Tabelas:
- notifications: uma notificação por usuário (lida/não lida, link, tipo)
- notification_rules: quais roles recebem cada tipo de notificação
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

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


class Notification(Base):
    """Notificação entregue a um usuário."""

    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    tipo: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    mensagem: Mapped[str] = mapped_column(Text, nullable=False)
    link: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    usuario_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), index=True, nullable=False
    )
    lida: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    criada_em: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    lida_em: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    usuario = relationship("User", foreign_keys=[usuario_id])


class NotificationRule(Base):
    """Regra: quais roles recebem notificações de um determinado tipo."""

    __tablename__ = "notification_rules"

    id: Mapped[int] = mapped_column(primary_key=True)
    tipo: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    roles_json: Mapped[str] = mapped_column(Text, nullable=False)  # '["admin","operador"]'
    ativo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
