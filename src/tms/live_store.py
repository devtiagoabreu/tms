"""Persistência e leitura do status ao vivo coletado dos teares."""

from __future__ import annotations

from datetime import datetime
from typing import Dict, Mapping, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from tms.core.live import LiveStatus, live_to_monitor_state
from tms.models.runtime import LiveStatusRecord


def _record(
    machine_id: int, live: LiveStatus, collected_at: Optional[datetime] = None
) -> LiveStatusRecord:
    return LiveStatusRecord(
        machine_id=machine_id,
        collected_at=collected_at or datetime.utcnow(),
        mac_type=live.mac_type,
        state=live_to_monitor_state(live),
        status=live.status,
        error=live.error,
        complete=live.complete,
        duration=live.duration,
        rpm=live.value("rpm"),
        efficiency=live.effic_shift,
        efficiency_24h=live.effic_24h,
        bits=dict(live.bits),
        data={k: v for k, v in live.data.items()},
        setup=dict(live.setup),
    )


def persist_live(
    db: Session,
    machines: Mapping[str, int],
    results: Mapping[str, LiveStatus],
    *,
    collected_at: Optional[datetime] = None,
) -> int:
    """Grava uma linha de `live_status` por resultado; devolve quantas gravou."""
    count = 0
    for name, live in results.items():
        machine_id = machines.get(name)
        if machine_id is None:
            continue
        db.add(_record(machine_id, live, collected_at))
        count += 1
    if count:
        db.flush()
    return count


def latest_live(db: Session) -> Dict[int, LiveStatusRecord]:
    """Status ao vivo mais recente por máquina."""
    rn = func.row_number().over(
        partition_by=LiveStatusRecord.machine_id,
        order_by=(LiveStatusRecord.collected_at.desc(), LiveStatusRecord.id.desc()),
    ).label("rn")
    sub = select(LiveStatusRecord.id, rn).subquery()
    ids = select(sub.c.id).where(sub.c.rn == 1)
    stmt = select(LiveStatusRecord).where(LiveStatusRecord.id.in_(ids))
    return {row.machine_id: row for row in db.execute(stmt).scalars()}


def record_to_live(record: LiveStatusRecord) -> LiveStatus:
    """Reconstrói um :class:`LiveStatus` a partir de uma linha persistida."""
    return LiveStatus(
        mac_type=record.mac_type,
        bits=dict(record.bits or {}),
        data=dict(record.data or {}),
        setup=dict(record.setup or {}),
        error=record.error,
    )


def latest_live_by_name(db: Session) -> Dict[str, LiveStatus]:
    """Último status ao vivo por `mac_name` (para o monitor)."""
    return {name: record_to_live(record) for name, record in latest_live_rows(db)}


def latest_live_rows(db: Session) -> list:
    """Lista ``(mac_name, LiveStatusRecord)`` do status mais recente por máquina."""
    from tms.models.masters import Machine

    stmt = (
        select(Machine.mac_name, LiveStatusRecord)
        .join(LiveStatusRecord, LiveStatusRecord.machine_id == Machine.id)
        .where(LiveStatusRecord.id.in_(_latest_ids(db)))
        .order_by(Machine.mac_name)
    )
    return db.execute(stmt).all()


def _latest_ids(db: Session):
    rn = func.row_number().over(
        partition_by=LiveStatusRecord.machine_id,
        order_by=(LiveStatusRecord.collected_at.desc(), LiveStatusRecord.id.desc()),
    ).label("rn")
    sub = select(LiveStatusRecord.id, rn).subquery()
    return select(sub.c.id).where(sub.c.rn == 1)
