"""Modelos para coleta diaria de teares (dashboard)."""

from __future__ import annotations

from datetime import datetime, date

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from tms.db.base import Base


class DailyCollectionRun(Base):
    """Execucao da coleta diaria por dia. Garante execucao unica por dia."""

    __tablename__ = "daily_collection_runs"
    __table_args__ = (
        UniqueConstraint("collection_date", name="uq_daily_collection_run_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    collection_date: Mapped[date] = mapped_column(Date, unique=True, index=True)
    status: Mapped[str] = mapped_column(String(16), default="pending")
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
    total_machines: Mapped[int] = mapped_column(Integer, default=0)
    success_count: Mapped[int] = mapped_column(Integer, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, default=0)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    items = relationship("DailyCollectionItem", back_populates="run", cascade="all, delete-orphan")


class DailyCollectionItem(Base):
    """Status por tear em uma coleta diaria."""

    __tablename__ = "daily_collection_items"
    __table_args__ = (
        UniqueConstraint("run_id", "machine_id", name="uq_daily_collection_item_run_machine"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("daily_collection_runs.id"), index=True)
    machine_id: Mapped[int] = mapped_column(ForeignKey("machines.id"), index=True)
    mac_name: Mapped[str] = mapped_column(String(32), index=True)
    mac_type: Mapped[str] = mapped_column(String(8), default="JAT")
    ip_addr: Mapped[str | None] = mapped_column(String(45))
    status: Mapped[str] = mapped_column(String(16), default="pending")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    error_reason: Mapped[str | None] = mapped_column(Text)
    collected_at: Mapped[datetime | None] = mapped_column(DateTime)
    data_json: Mapped[dict | None] = mapped_column(JSON)
    in_retry_queue: Mapped[bool] = mapped_column(Boolean, default=False)
    last_retry_at: Mapped[datetime | None] = mapped_column(DateTime)

    run = relationship("DailyCollectionRun", back_populates="items")
    machine = relationship("Machine")


class DailyLoomData(Base):
    """Dados coletados diariamente dos teares (para exibicao no dashboard)."""

    __tablename__ = "daily_loom_data"
    __table_args__ = (
        UniqueConstraint("collection_date", "machine_id", name="uq_daily_loom_data_date_machine"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    collection_date: Mapped[date] = mapped_column(Date, index=True)
    machine_id: Mapped[int] = mapped_column(ForeignKey("machines.id"), index=True)
    mac_name: Mapped[str] = mapped_column(String(32), index=True)
    source: Mapped[str] = mapped_column(String(16), default="live")  # agg_shift|daily_raw|history|live
    shift_id: Mapped[str | None] = mapped_column(String(32), index=True)
    style: Mapped[str | None] = mapped_column(String(64))
    beam: Mapped[str | None] = mapped_column(String(32))
    production: Mapped[float | None] = mapped_column(Float)
    efficiency: Mapped[float | None] = mapped_column(Float)
    rpm: Mapped[float | None] = mapped_column(Float)
    run_time_min: Mapped[float | None] = mapped_column(Float)
    stop_time_min: Mapped[float | None] = mapped_column(Float)
    total_stop_ct: Mapped[int | None] = mapped_column(Integer)
    total_stop_tm_min: Mapped[float | None] = mapped_column(Float)
    trama_stops: Mapped[int | None] = mapped_column(Integer)
    trama_stops_min: Mapped[float | None] = mapped_column(Float)
    urdume_stops: Mapped[int | None] = mapped_column(Integer)
    urdume_stops_min: Mapped[float | None] = mapped_column(Float)
    outros_stops: Mapped[int | None] = mapped_column(Integer)
    outros_stops_min: Mapped[float | None] = mapped_column(Float)
    raw_data: Mapped[dict | None] = mapped_column(JSON)
    collected_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    machine = relationship("Machine")
