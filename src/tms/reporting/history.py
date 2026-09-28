"""Carregadores de histórico (stophistory e showstyle).

- `stop_events` (`stop_history/<data>/<mac>.txt`) → eventos de parada;
- `agg_shift`/`operator_daily` → linhas-base da matriz showstyle
  (quais estilos cada tear operou em cada turno/dia).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from tms.ingest.shift_file import parse_shift_line
from tms.models.masters import Machine, Operator
from tms.models.runtime import AggShift, OperatorDaily, StopEvent


@dataclass(frozen=True)
class StopEventRow:
    """Evento de parada para o stophistory.

    ``stop_time``/``run_time`` são segundos desde 00:00 (0 quando o campo do
    arquivo é ``-``). ``raw_code`` é o código cru (ex.: ``2153``).
    """

    mac_name: str
    mac_type: str
    day: str  # YYYY.MM.DD
    stop_time: int
    run_time: int
    raw_code: str


def load_stop_events(
    db: Session,
    *,
    day_from: Optional[str] = None,
    day_to: Optional[str] = None,
    mac_name: Optional[str] = None,
) -> list[StopEventRow]:
    """Carrega `stop_events` (join `machines`) em ordem dia/tear/evento."""
    stmt = (
        select(StopEvent, Machine.mac_name, Machine.mac_type)
        .join(Machine, Machine.id == StopEvent.machine_id)
        .order_by(StopEvent.day, Machine.mac_name, StopEvent.id)
    )
    if mac_name:
        stmt = stmt.where(Machine.mac_name == mac_name)
    if day_from:
        stmt = stmt.where(StopEvent.day >= day_from)
    if day_to:
        stmt = stmt.where(StopEvent.day <= day_to)
    return [
        StopEventRow(
            mac_name=name,
            mac_type=mac_type,
            day=ev.day,
            stop_time=ev.stop_time or 0,
            run_time=ev.run_time or 0,
            raw_code=ev.raw_code or "",
        )
        for ev, name, mac_type in db.execute(stmt)
    ]


@dataclass(frozen=True)
class ShowstyleRow:
    """Registro-base da matriz showstyle (um por tear × turno × estilo)."""

    key: str  # shift_id (data=shift) ou YYYY.MM.DD (data=operator)
    mac_name: str
    operator_name: Optional[str] = None
    style: Optional[str] = None


def load_showstyle_records(
    db: Session,
    *,
    source: str = "shift",
    day_from: Optional[str] = None,
    day_to: Optional[str] = None,
    mac_name: Optional[str] = None,
) -> list[ShowstyleRow]:
    """Linhas da matriz a partir de `agg_shift` (``source="shift"``) ou
    `operator_daily` (``source="operator"``, sem granularidade de turno).
    """
    if source == "shift":
        stmt = select(AggShift.shift_id, Machine.mac_name, AggShift.style).join(
            Machine, Machine.id == AggShift.machine_id
        )
        if mac_name:
            stmt = stmt.where(Machine.mac_name == mac_name)
        if day_from:
            stmt = stmt.where(AggShift.shift_id >= day_from)
        if day_to:
            stmt = stmt.where(AggShift.shift_id <= f"{day_to}.9")
        stmt = stmt.order_by(AggShift.shift_id, Machine.mac_name, AggShift.id)
        return [
            ShowstyleRow(key=shift_id or "", mac_name=name, style=style)
            for shift_id, name, style in db.execute(stmt)
        ]
    if source == "operator":
        stmt = (
            select(
                OperatorDaily.day,
                Machine.mac_name,
                Operator.name,
                OperatorDaily.raw_line,
            )
            .join(Machine, Machine.id == OperatorDaily.machine_id)
            .join(Operator, Operator.id == OperatorDaily.operator_id)
        )
        if mac_name:
            stmt = stmt.where(Machine.mac_name == mac_name)
        if day_from:
            stmt = stmt.where(OperatorDaily.day >= day_from)
        if day_to:
            stmt = stmt.where(OperatorDaily.day <= day_to)
        stmt = stmt.order_by(OperatorDaily.day, Operator.name, Machine.mac_name)

        rows = []
        for day, name, ope, raw_line in db.execute(stmt):
            style = None
            if raw_line:
                parsed = parse_shift_line(raw_line)
                if parsed is not None:
                    style = parsed.style or None
            rows.append(ShowstyleRow(key=day, mac_name=name, operator_name=ope, style=style))
        return rows
    raise ValueError(f"fonte showstyle inválida: {source}")