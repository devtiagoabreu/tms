"""Modelos de roles e permissões (TMS 8.0).

Permite definir permissões granulares e associá-las a roles.
Ex: teares.ver, teares.editar, coletar.executar, menus.configurar, etc.
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


class Permission(Base):
    """Permissão granular do sistema."""

    __tablename__ = "permissions"

    id: Mapped[int] = mapped_column(primary_key=True)
    chave: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)  # ex: teares.ver
    descricao: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    modulo: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)  # ex: teares, menus, coletar
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    role_permissions = relationship(
        "RolePermission", back_populates="permission", cascade="all, delete-orphan"
    )


class RolePermission(Base):
    """Associação entre uma role e uma permissão."""

    __tablename__ = "role_permissions"
    __table_args__ = (
        UniqueConstraint("role", "permission_id", name="uq_role_permission"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    role: Mapped[str] = mapped_column(String(32), nullable=False, index=True)  # admin|operador|visualizador
    permission_id: Mapped[int] = mapped_column(
        ForeignKey("permissions.id"), index=True, nullable=False
    )
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    permission = relationship("Permission", back_populates="role_permissions")
