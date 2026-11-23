"""Tabelas mestre (máquinas, estilos, operadores, turnos, configurações)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from tms.db.base import Base


class Machine(Base):
    __tablename__ = "machines"

    id: Mapped[int] = mapped_column(primary_key=True)
    mac_name: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    mac_type: Mapped[str] = mapped_column(String(8), default="JAT")  # JAT | LWT
    ip_addr: Mapped[str | None] = mapped_column(String(45))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_double: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    snapshots = relationship("MachineSnapshot", back_populates="machine")
    group_members = relationship(
        "MachineGroupMember", back_populates="machine", cascade="all, delete-orphan"
    )

    @property
    def group(self):
        """Retorna o(s) grupo(s) ao qual o tear pertence."""
        return [m.group for m in self.group_members if m.group]


class Style(Base):
    __tablename__ = "styles"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    beam_type: Mapped[int] = mapped_column(Integer, default=1)  # 2 = top-beam loom
    unit: Mapped[int] = mapped_column(Integer, default=0)  # 0 PICK / 1 METER / 2 YARD
    density: Mapped[str | None] = mapped_column(String(32))  # style_mst.txt (2ª coluna)
    doff_len: Mapped[int | None] = mapped_column(Integer)  # style_mst.txt (3ª coluna)


class IpRange(Base):
    """Faixa de IP de teares (setting/ipaddress.txt: `a b c start end`)."""

    __tablename__ = "ip_ranges"

    id: Mapped[int] = mapped_column(primary_key=True)
    a: Mapped[int] = mapped_column(Integer)
    b: Mapped[int] = mapped_column(Integer)
    c: Mapped[int] = mapped_column(Integer)
    start: Mapped[int] = mapped_column(Integer)
    end: Mapped[int] = mapped_column(Integer)

    def expand(self) -> list[str]:
        return [f"{self.a}.{self.b}.{self.c}.{i}" for i in range(self.start, self.end + 1)]


class Operator(Base):
    """Operador (tecelão, contra-mestre, supervisor, etc.)."""

    __tablename__ = "operators"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(16), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(64))
    role: Mapped[str | None] = mapped_column(
        String(32), default="tecelao"
    )  # tecelao | contra_mestre | supervisor
    shift_day: Mapped[str | None] = mapped_column(String(16))  # ope_num no legado
    group_id: Mapped[int | None] = mapped_column(
        ForeignKey("machine_groups.id"), nullable=True, index=True
    )
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    group = relationship("MachineGroup")


class ShiftSchedule(Base):
    """Escala de turnos (scanset/shiftset + bloco 'shift' dos arquivos de máquina)."""

    __tablename__ = "shift_schedules"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True)
    shift_mode: Mapped[int] = mapped_column(Integer, default=0)
    simple: Mapped[str | None] = mapped_column(Text)  # "3 05:00 14:00 23:35 ..."
    day_start_time: Mapped[str] = mapped_column(String(8), default="6:0")
    schedule_json: Mapped[dict | None] = mapped_column(JSON)  # DAY_0..DAY_6, NAME_0..5


class Setting(Base):
    """Chave/valor livre (language, expire, service, security_dir, member)."""

    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class ReportPref(Base):
    """Prefs de relatório (antigo setting/selitem.txt), por instalação."""

    __tablename__ = "report_prefs"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(32), index=True)
    value: Mapped[str] = mapped_column(Text)

    # Representa: item2, item, item3, detail, color, beam_type, unit, period, ...