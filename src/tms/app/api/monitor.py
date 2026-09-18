"""Endpoint de monitoramento ao vivo por tear."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from tms.app.api.schemas import LiveStatusRecordOut, MonitorItemOut
from tms.collector import DEFAULT_TIMEOUT, collect
from tms.db.base import get_db
from tms.live_store import latest_live_by_name, latest_live_rows
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
    stored: bool = Query(False, description="usa o último status ao vivo persistido"),
    timeout: float = Query(DEFAULT_TIMEOUT, gt=0),
    db: Session = Depends(get_db),
) -> list[MonitorItemOut]:
    """Estado atual de cada tear (frescura do snapshot + parada em aberto).

    - `live=true`: coleta agora nos teares com IP cadastrado (lento);
    - `stored=true`: usa o último status gravado em `live_status`;
    - ambos sobrepõem o estado calculado a partir do banco.
    """
    if live:
        live_data = collect(_live_machines(db), timeout=timeout)
    elif stored:
        live_data = latest_live_by_name(db)
    else:
        live_data = None
    items = build_monitor(
        db, offline_after_s=offline_after_s, lang=lang, live=live_data
    )
    return [MonitorItemOut(**item) for item in items]


@router.get("/live-status", response_model=list[LiveStatusRecordOut])
def live_status(db: Session = Depends(get_db)) -> list[LiveStatusRecordOut]:
    """Último status ao vivo persistido por tear."""
    return [
        LiveStatusRecordOut(
            mac_name=name,
            **{k: v for k, v in record.__dict__.items() if not k.startswith("_")},
        )
        for name, record in latest_live_rows(db)
    ]
