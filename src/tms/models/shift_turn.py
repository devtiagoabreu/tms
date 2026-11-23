"""Cadastro de turnos de producao.

Permite definir turnos com hora de inicio/fim, dias da semana em que valem,
ativo/inativo e se o turno atravessa a meia-noite (ex.: turno C das 23:35
ate as 05:00 do dia seguinte).
"""

from __future__ import annotations

from sqlalchemy import Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from tms.db.base import Base


class ShiftTurn(Base):
    """Um turno de producao."""

    __tablename__ = "shift_turns"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(16), nullable=False)  # A, B, C
    start_time: Mapped[str] = mapped_column(String(5), nullable=False)  # HH:MM
    end_time: Mapped[str] = mapped_column(String(5), nullable=False)  # HH:MM
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Mascara de bits: bit0=domingo ... bit6=snado
    days_mask: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    wraps_midnight: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )  # turno passa da meia-noite
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
