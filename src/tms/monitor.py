"""Serviço de monitoramento ao vivo (estado atual por tear)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from tms.core.formulas import rpm_from_agg
from tms.core.state import color, decide_state, label
from tms.core.stopcodes import get_stop_cause
from tms.models.masters import Machine
from tms.models.runtime import AggShift, MachineSnapshot, StopEvent

DEFAULT_OFFLINE_AFTER_S = 900


def _latest_snapshots(db: Session) -> Dict[int, MachineSnapshot]:
    latest = (
        select(
            MachineSnapshot.machine_id,
            func.max(MachineSnapshot.get_time).label("get_time"),
        )
        .group_by(MachineSnapshot.machine_id)
        .subquery()
    )
    stmt = select(MachineSnapshot).join(
        latest,
        (MachineSnapshot.machine_id == latest.c.machine_id)
        & (MachineSnapshot.get_time == latest.c.get_time),
    )
    found: Dict[int, MachineSnapshot] = {}
    for snap in db.execute(stmt).scalars():
        found.setdefault(snap.machine_id, snap)
    return found


def _latest_stops(db: Session) -> Dict[int, StopEvent]:
    rn = func.row_number().over(
        partition_by=StopEvent.machine_id,
        order_by=(StopEvent.day.desc(), StopEvent.stop_time.desc()),
    ).label("rn")
    sub = select(StopEvent.id, rn).subquery()
    ids = select(sub.c.id).where(sub.c.rn == 1)
    stmt = select(StopEvent).where(StopEvent.id.in_(ids))
    return {event.machine_id: event for event in db.execute(stmt).scalars()}


def _latest_agg(db: Session) -> Dict[int, AggShift]:
    rn = func.row_number().over(
        partition_by=AggShift.machine_id, order_by=AggShift.shift_id.desc()
    ).label("rn")
    sub = select(AggShift.id, rn).subquery()
    ids = select(sub.c.id).where(sub.c.rn == 1)
    stmt = select(AggShift).where(AggShift.id.in_(ids))
    return {agg.machine_id: agg for agg in db.execute(stmt).scalars()}


def _open_stop(event: Optional[StopEvent]) -> bool:
    # run_time == 0 ("-" no legado) significa parada ainda em andamento.
    return bool(event and event.stop_time and not event.run_time)


def build_monitor(
    db: Session,
    *,
    now: Optional[datetime] = None,
    offline_after_s: int = DEFAULT_OFFLINE_AFTER_S,
    lang: str = "pt",
) -> List[Dict[str, Any]]:
    """Lista o estado atual de cada tear (para API/dashboard)."""
    now = now or datetime.utcnow()
    machines = db.execute(select(Machine).order_by(Machine.mac_name)).scalars().all()
    snaps = _latest_snapshots(db)
    stops = _latest_stops(db)
    aggs = _latest_agg(db)

    result: List[Dict[str, Any]] = []
    for machine in machines:
        snap = snaps.get(machine.id)
        event = stops.get(machine.id)
        agg = aggs.get(machine.id)
        open_stop = _open_stop(event)

        last_seen = snap.get_time if snap else None
        state = decide_state(
            last_seen=last_seen,
            now=now,
            offline_after_s=offline_after_s,
            has_open_stop=open_stop,
        )

        stop_info = None
        if open_stop and event is not None:
            duration = None
            if event.stop_start is not None:
                duration = round((now - event.stop_start).total_seconds() / 60.0, 1)
            stop_info = {
                "raw_code": event.raw_code,
                "cause": get_stop_cause(event.raw_code, machine.mac_type, lang),
                "started_at": event.stop_start.isoformat() if event.stop_start else None,
                "duration_min": duration,
            }

        result.append(
            {
                "mac_name": machine.mac_name,
                "mac_type": machine.mac_type,
                "active": machine.active,
                "state": state,
                "state_label": label(state, lang),
                "color": color(state),
                "last_seen": last_seen.isoformat() if last_seen else None,
                "age_min": (
                    round((now - last_seen).total_seconds() / 60.0, 1) if last_seen else None
                ),
                "shift_id": snap.shift_id if snap else None,
                "style": snap.style if snap else None,
                "beam": snap.beam if snap else None,
                "production": (
                    round((agg.seisan_1 or 0.0) + (agg.off_prod_1 or 0.0), 1) if agg else None
                ),
                "efficiency": round(agg.effic, 1) if agg and agg.effic is not None else None,
                "rpm": (
                    round(rpm_from_agg(agg.seisan_1 or 0.0, agg.run_tm or 0.0), 1) if agg else None
                ),
                "stop": stop_info,
            }
        )
    return result
