"""Endpoint de monitoramento ao vivo por tear."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from tms.app.api.schemas import MonitorItemOut
from tms.collector import DEFAULT_TIMEOUT, collect
from tms.db.base import get_db
from tms.monitor import DEFAULT_OFFLINE_AFTER_S, build_monitor
from tms.models.masters import Machine

router = APIRouter(prefix="/api", tags=["monitor"])


def _live_machines(db: Session) -> list[tuple[str, str]]:
    rows = db.execute(
        select(Machine.mac_name, Machine.ip_addr).where(Machine.ip_addr.is_not(None))
    ).all()
    return [(name, ip) for name, ip in rows if ip]


@router.get("/monitor", response_model=list[MonitorItemOut])
def monitor(
    offline_after_s: int = Query(DEFAULT_OFFLINE_AFTER_S, ge=0),
    lang: str = Query("pt"),
    live: bool = Query(False, description="coleta o estado direto dos teares (lento)"),
    timeout: float = Query(DEFAULT_TIMEOUT, gt=0),
    db: Session = Depends(get_db),
) -> list[MonitorItemOut]:
    """Estado atual de cada tear (frescura do snapshot + parada em aberto).

    Com `live=true`, faz a coleta ao vivo nos teares que têm IP cadastrado e
    sobrepõe o estado calculado a partir do banco.
    """
    live_data = collect(_live_machines(db), timeout=timeout) if live else None
    items = build_monitor(
        db, offline_after_s=offline_after_s, lang=lang, live=live_data
    )
    return [MonitorItemOut(**item) for item in items]
