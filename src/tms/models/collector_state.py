"""Estado do coletor contínuo de status ao vivo dos teares.

Persiste quando o coletor está ligado/desligado, a última coleta realizada
e a próxima coleta prevista, para que o dashboard possa exibir essas
informações ao operador.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from tms.db.base import Base


class CollectorState(Base):
    """Única linha que guarda o estado do coletor contínuo."""

    __tablename__ = "collector_state"

    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    interval_s: Mapped[int] = mapped_column(Integer, default=60, nullable=False)
    last_collected_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True
    )
    next_collect_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )
