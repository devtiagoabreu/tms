"""Tabelas de runtime: snapshots, eventos de parada, brutos e agregados."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from tms.db.base import Base


class MachineSnapshot(Base):
    """Equivalente a current/current.txt (snapshot real por tear)."""

    __tablename__ = "machine_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    machine_id: Mapped[int] = mapped_column(ForeignKey("machines.id"), index=True)
    shift_id: Mapped[str | None] = mapped_column(String(32), index=True)  # ex.: 2026.09.17.1
    get_time: Mapped[datetime | None] = mapped_column(DateTime)
    sys_time: Mapped[datetime | None] = mapped_column(DateTime)
    rtc_time: Mapped[datetime | None] = mapped_column(DateTime)
    style: Mapped[str | None] = mapped_column(String(64))
    beam: Mapped[str | None] = mapped_column(String(32))
    ubeam: Mapped[str | None] = mapped_column(String(32))
    s_beam: Mapped[str | None] = mapped_column(String(32))
    r_beam: Mapped[str | None] = mapped_column(String(32))
    cloth_len: Mapped[str | None] = mapped_column(String(32))
    cut_len: Mapped[str | None] = mapped_column(String(32))
    doff_fcst: Mapped[int | None] = mapped_column(Integer)
    wout_fcst: Mapped[int | None] = mapped_column(Integer)
    uwout_fcst: Mapped[int | None] = mapped_column(Integer)
    raw: Mapped[dict | None] = mapped_column(JSON)  # payload completo da coleta

    machine = relationship("Machine", back_populates="snapshots")


class StopEvent(Base):
    """Evento de parada (stop_history). stop_time/run_time em segundos."""

    __tablename__ = "stop_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    machine_id: Mapped[int] = mapped_column(ForeignKey("machines.id"), index=True)
    shift_id: Mapped[str | None] = mapped_column(String(32), index=True)
    day: Mapped[str] = mapped_column(String(10), index=True)  # YYYY.MM.DD
    stop_time: Mapped[int] = mapped_column(Integer)  # segundos
    run_time: Mapped[int] = mapped_column(Integer)  # segundos
    raw_code: Mapped[str] = mapped_column(String(16))
    fixed: Mapped[bool] = mapped_column(default=False)  # fixed | unfix
    stop_start: Mapped[datetime | None] = mapped_column(DateTime)
    stop_end: Mapped[datetime | None] = mapped_column(DateTime)
    duration_min: Mapped[float | None] = mapped_column(Float)


class DailyRaw(Base):
    """Registro bruto por tear/dia (shift/<yyyymmdd>.<n>.txt)."""

    __tablename__ = "daily_raw"

    id: Mapped[int] = mapped_column(primary_key=True)
    machine_id: Mapped[int] = mapped_column(ForeignKey("machines.id"), index=True)
    day: Mapped[str] = mapped_column(String(10), index=True)
    seisan: Mapped[dict | None] = mapped_column(JSON)  # seisan(4) + off_prod(3)
    run_tm: Mapped[int | None] = mapped_column(Integer)  # segundos
    stop_ttm: Mapped[int | None] = mapped_column(Integer)  # segundos
    s_ct: Mapped[list | None] = mapped_column(JSON)  # códigos crus (40/31)
    s_tm: Mapped[list | None] = mapped_column(JSON)
    raw_line: Mapped[str | None] = mapped_column(Text)
    collected_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class AggShift(Base):
    """Linha agregada por turno (shift-shift/<shift>.txt).

    run_tm/stop_ttm em minutos com 3 casas; seisan/off_prod já /10.
    """

    __tablename__ = "agg_shift"

    id: Mapped[int] = mapped_column(primary_key=True)
    shift_id: Mapped[str] = mapped_column(String(32), index=True)  # ex.: 2026.09.17.0
    machine_id: Mapped[int | None] = mapped_column(ForeignKey("machines.id"), index=True)
    operator_id: Mapped[int | None] = mapped_column(ForeignKey("operators.id"), index=True)

    style: Mapped[str | None] = mapped_column(String(64))
    beam: Mapped[str | None] = mapped_column(String(32))
    ubeam: Mapped[str | None] = mapped_column(String(32))

    seisan_1: Mapped[float | None] = mapped_column(Float)
    seisan_2: Mapped[float | None] = mapped_column(Float)
    seisan_3: Mapped[float | None] = mapped_column(Float)
    off_prod_1: Mapped[float | None] = mapped_column(Float)
    off_prod_2: Mapped[float | None] = mapped_column(Float)
    off_prod_3: Mapped[float | None] = mapped_column(Float)

    run_tm: Mapped[float | None] = mapped_column(Float)  # minutos
    stop_ttm: Mapped[float | None] = mapped_column(Float)  # minutos
    effic: Mapped[float | None] = mapped_column(Float)

    stop_ct: Mapped[list | None] = mapped_column(JSON)  # 12
    stop_tm: Mapped[list | None] = mapped_column(JSON)  # 12 (minutos)
    wf1_ct: Mapped[list | None] = mapped_column(JSON)  # 6|4
    wf1_tm: Mapped[list | None] = mapped_column(JSON)
    wf2_ct: Mapped[list | None] = mapped_column(JSON)
    wf2_tm: Mapped[list | None] = mapped_column(JSON)
    lh_ct: Mapped[list | None] = mapped_column(JSON)
    lh_tm: Mapped[list | None] = mapped_column(JSON)