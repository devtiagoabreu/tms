"""Endpoint de status do coletor contínuo de status ao vivo."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from tms.app.deps.auth import require_roles
from tms.db.base import get_db
from tms.models.auth import UserRole
from tms.models.collector_state import CollectorState

router = APIRouter(prefix="/api/collector", tags=["collector"])


def _iso(value) -> str | None:
    return value.isoformat() if value else None


@router.get("/status")
def collector_status(
    db: Session = Depends(get_db),
    _=Depends(require_roles(UserRole.admin)),
) -> dict:
    """Retorna o estado do coletor contínuo: ligado/desligado, última e próxima coleta."""
    state = db.get(CollectorState, 1)
    if state is None:
        return {
            "enabled": False,
            "interval_s": 0,
            "last_collected_at": None,
            "next_collect_at": None,
        }
    return {
        "enabled": state.enabled,
        "interval_s": state.interval_s,
        "last_collected_at": _iso(state.last_collected_at),
        "next_collect_at": _iso(state.next_collect_at),
        "updated_at": _iso(state.updated_at),
    }
