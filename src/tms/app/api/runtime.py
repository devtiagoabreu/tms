"""Endpoints de leitura do runtime (snapshots, brutos, agregados e paradas)."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from tms.app.api.schemas import (
    AggShiftOut,
    DailyRawOut,
    MachineOut,
    OperatorDailyOut,
    SnapshotOut,
    StopEventOut,
    serialize,
)
from tms.db.base import get_db
from tms.models.masters import Machine, Operator
from tms.models.runtime import (
    AggShift,
    DailyRaw,
    MachineSnapshot,
    OperatorDaily,
    StopEvent,
)

router = APIRouter(prefix="/api", tags=["runtime"])

Limit = Query(100, ge=1, le=1000)
Offset = Query(0, ge=0)


def _by_shift_id(stmt: Select, shift_id: Optional[str], day_from: Optional[str], day_to: Optional[str]) -> Select:
    if shift_id:
        stmt = stmt.where(AggShift.shift_id == shift_id)
    if day_from:
        stmt = stmt.where(AggShift.shift_id >= day_from)
    if day_to:
        stmt = stmt.where(AggShift.shift_id <= f"{day_to}.9")
    return stmt


@router.get("/machines", response_model=list[MachineOut])
def list_machines(db: Session = Depends(get_db)) -> list[Machine]:
    return list(db.execute(select(Machine).order_by(Machine.mac_name)).scalars())


@router.get("/machines/{mac_name}", response_model=MachineOut)
def get_machine(mac_name: str, db: Session = Depends(get_db)) -> Machine:
    machine = db.execute(
        select(Machine).where(Machine.mac_name == mac_name)
    ).scalar_one_or_none()
    if machine is None:
        raise HTTPException(status_code=404, detail="machine not found")
    return machine


@router.get("/machines/{mac_name}/snapshot", response_model=SnapshotOut)
def latest_snapshot(mac_name: str, db: Session = Depends(get_db)) -> SnapshotOut:
    row = db.execute(
        select(MachineSnapshot, Machine.mac_name)
        .join(Machine, Machine.id == MachineSnapshot.machine_id)
        .where(Machine.mac_name == mac_name)
        .order_by(MachineSnapshot.get_time.desc().nullslast())
        .limit(1)
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="no snapshot for machine")
    return serialize(row[0], SnapshotOut, row[1])


@router.get("/snapshots", response_model=list[SnapshotOut])
def list_snapshots(
    mac_name: Optional[str] = None,
    shift_id: Optional[str] = None,
    day_from: Optional[str] = None,
    day_to: Optional[str] = None,
    limit: int = Limit,
    offset: int = Offset,
    db: Session = Depends(get_db),
) -> list[SnapshotOut]:
    stmt = select(MachineSnapshot, Machine.mac_name).join(
        Machine, Machine.id == MachineSnapshot.machine_id
    )
    if mac_name:
        stmt = stmt.where(Machine.mac_name == mac_name)
    if shift_id:
        stmt = stmt.where(MachineSnapshot.shift_id == shift_id)
    if day_from:
        stmt = stmt.where(MachineSnapshot.shift_id >= day_from)
    if day_to:
        stmt = stmt.where(MachineSnapshot.shift_id <= f"{day_to}.9")
    stmt = stmt.order_by(MachineSnapshot.get_time.desc().nullslast()).limit(limit).offset(offset)
    return [serialize(obj, SnapshotOut, mac) for obj, mac in db.execute(stmt)]


@router.get("/daily-raw", response_model=list[DailyRawOut])
def list_daily_raw(
    mac_name: Optional[str] = None,
    day: Optional[str] = None,
    shift_id: Optional[str] = None,
    day_from: Optional[str] = None,
    day_to: Optional[str] = None,
    limit: int = Limit,
    offset: int = Offset,
    db: Session = Depends(get_db),
) -> list[DailyRawOut]:
    stmt = select(DailyRaw, Machine.mac_name).join(Machine, Machine.id == DailyRaw.machine_id)
    if mac_name:
        stmt = stmt.where(Machine.mac_name == mac_name)
    if day:
        stmt = stmt.where(DailyRaw.day == day)
    if shift_id:
        stmt = stmt.where(DailyRaw.shift_id == shift_id)
    if day_from:
        stmt = stmt.where(DailyRaw.day >= day_from)
    if day_to:
        stmt = stmt.where(DailyRaw.day <= day_to)
    stmt = (
        stmt.order_by(DailyRaw.day.desc(), DailyRaw.shift_id, Machine.mac_name)
        .limit(limit)
        .offset(offset)
    )
    return [serialize(obj, DailyRawOut, mac) for obj, mac in db.execute(stmt)]


@router.get("/agg-shift", response_model=list[AggShiftOut])
def list_agg_shift(
    mac_name: Optional[str] = None,
    shift_id: Optional[str] = None,
    day_from: Optional[str] = None,
    day_to: Optional[str] = None,
    limit: int = Limit,
    offset: int = Offset,
    db: Session = Depends(get_db),
) -> list[AggShiftOut]:
    stmt = select(AggShift, Machine.mac_name).join(
        Machine, Machine.id == AggShift.machine_id, isouter=True
    )
    if mac_name:
        stmt = stmt.where(Machine.mac_name == mac_name)
    stmt = _by_shift_id(stmt, shift_id, day_from, day_to)
    stmt = stmt.order_by(AggShift.shift_id.desc(), Machine.mac_name).limit(limit).offset(offset)
    return [serialize(obj, AggShiftOut, mac) for obj, mac in db.execute(stmt)]


@router.get("/stop-events", response_model=list[StopEventOut])
def list_stop_events(
    mac_name: Optional[str] = None,
    day: Optional[str] = None,
    shift_id: Optional[str] = None,
    raw_code: Optional[str] = None,
    day_from: Optional[str] = None,
    day_to: Optional[str] = None,
    limit: int = Limit,
    offset: int = Offset,
    db: Session = Depends(get_db),
) -> list[StopEventOut]:
    stmt = select(StopEvent, Machine.mac_name).join(Machine, Machine.id == StopEvent.machine_id)
    if mac_name:
        stmt = stmt.where(Machine.mac_name == mac_name)
    if day:
        stmt = stmt.where(StopEvent.day == day)
    if shift_id:
        stmt = stmt.where(StopEvent.shift_id == shift_id)
    if raw_code:
        stmt = stmt.where(StopEvent.raw_code == raw_code)
    if day_from:
        stmt = stmt.where(StopEvent.day >= day_from)
    if day_to:
        stmt = stmt.where(StopEvent.day <= day_to)
    stmt = (
        stmt.order_by(StopEvent.day.desc(), StopEvent.stop_time, Machine.mac_name)
        .limit(limit)
        .offset(offset)
    )
    return [serialize(obj, StopEventOut, mac) for obj, mac in db.execute(stmt)]


@router.get("/operator-daily", response_model=list[OperatorDailyOut])
def list_operator_daily(
    mac_name: Optional[str] = None,
    day: Optional[str] = None,
    operator_code: Optional[str] = None,
    day_from: Optional[str] = None,
    day_to: Optional[str] = None,
    limit: int = Limit,
    offset: int = Offset,
    db: Session = Depends(get_db),
) -> list[OperatorDailyOut]:
    stmt = (
        select(OperatorDaily, Machine.mac_name)
        .join(Machine, Machine.id == OperatorDaily.machine_id)
        .join(Operator, Operator.id == OperatorDaily.operator_id)
    )
    if mac_name:
        stmt = stmt.where(Machine.mac_name == mac_name)
    if operator_code:
        stmt = stmt.where(Operator.code == operator_code)
    if day:
        stmt = stmt.where(OperatorDaily.day == day)
    if day_from:
        stmt = stmt.where(OperatorDaily.day >= day_from)
    if day_to:
        stmt = stmt.where(OperatorDaily.day <= day_to)
    stmt = (
        stmt.order_by(OperatorDaily.day.desc(), Machine.mac_name)
        .limit(limit)
        .offset(offset)
    )
    return [serialize(obj, OperatorDailyOut, mac) for obj, mac in db.execute(stmt)]
