"""Modelos de navegação (menus dinâmicos) — inspirado no pdmtextil.

Permite cadastrar menus e itens no banco, agrupados por role, e opcionalmente
fazer "fork" dos menus de um role para um usuário específico (menus pessoais).
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
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from tms.db.base import Base


class Menu(Base):
    """Menu de navegação (grupo). Pode ser global (por role) ou pessoal (usuário)."""

    __tablename__ = "menus"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(64), nullable=False)
    icon: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    url: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    ordem: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    role: Mapped[Optional[str]] = mapped_column(
        String(32), nullable=True
    )  # None = visível para todos os autenticados
    usuario_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )  # se preenchido, é menu pessoal do usuário
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    items = relationship(
        "MenuItem", back_populates="menu", cascade="all, delete-orphan"
    )
    usuario = relationship("User", foreign_keys=[usuario_id])

    __table_args__ = (
        UniqueConstraint("title", "usuario_id", name="uq_menu_title_usuario"),
    )


class MenuItem(Base):
    """Item dentro de um menu (link ou subgrupo)."""

    __tablename__ = "menu_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    menu_id: Mapped[int] = mapped_column(ForeignKey("menus.id"), index=True)
    title: Mapped[str] = mapped_column(String(64), nullable=False)
    url: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    icon: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    ordem: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    menu = relationship("Menu", back_populates="items")
