"""Endpoint de monitoramento ao vivo por tear."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from tms.app.api.schemas import MonitorItemOut
from tms.db.base import get_db
from tms.monitor import DEFAULT_OFFLINE_AFTER_S, build_monitor

router = APIRouter(prefix="/api", tags=["monitor"])


@router.get("/monitor", response_model=list[MonitorItemOut])
def monitor(
    offline_after_s: int = Query(DEFAULT_OFFLINE_AFTER_S, ge=0),
    lang: str = Query("pt"),
    db: Session = Depends(get_db),
) -> list[MonitorItemOut]:
    """Estado atual de cada tear (frescura do snapshot + parada em aberto)."""
    return [MonitorItemOut(**item) for item in build_monitor(db, offline_after_s=offline_after_s, lang=lang)]
