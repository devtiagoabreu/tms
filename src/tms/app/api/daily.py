"""Endpoints do dashboard de coleta diaria."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from tms.app.deps.auth import require_roles
from tms.db.base import get_db
from tms.models.auth import UserRole
from tms.models.daily import DailyCollectionItem, DailyCollectionRun, DailyLoomData
from tms.services.daily_collection import (
    collect_daily_data,
    get_yesterday,
    retry_pending,
)

router = APIRouter(prefix="/api/daily", tags=["daily"])


def _iso(value) -> Optional[str]:
    return value.isoformat() if value else None


def _item_out(item: DailyCollectionItem) -> dict:
    return {
        "mac_name": item.mac_name,
        "mac_type": item.mac_type,
        "ip_addr": item.ip_addr,
        "status": item.status,
        "attempts": item.attempts,
        "error": item.error_reason,
        "collected_at": _iso(item.collected_at),
        "in_retry_queue": item.in_retry_queue,
        "last_retry_at": _iso(item.last_retry_at),
    }


def _run_out(run: DailyCollectionRun, items: list[DailyCollectionItem]) -> dict:
    return {
        "collection_date": run.collection_date.isoformat(),
        "status": run.status,
        "started_at": _iso(run.started_at),
        "finished_at": _iso(run.finished_at),
        "total_machines": run.total_machines,
        "success_count": run.success_count,
        "failed_count": run.failed_count,
        "retry_count": run.retry_count,
        "items": [_item_out(i) for i in items],
    }


def _items_of(db: Session, run_id: int) -> list[DailyCollectionItem]:
    return list(
        db.execute(
            select(DailyCollectionItem)
            .where(DailyCollectionItem.run_id == run_id)
            .order_by(DailyCollectionItem.mac_name)
        ).scalars()
    )


def _summary(run: DailyCollectionRun, rows: list[DailyLoomData], items: list[DailyCollectionItem]) -> dict:
    efficiencies = [r.efficiency for r in rows if r.efficiency is not None]
    rpms = [r.rpm for r in rows if r.rpm is not None]
    production = [r.production for r in rows if r.production is not None]

    def total(attr: str):
        values = [getattr(r, attr) for r in rows if getattr(r, attr) is not None]
        return round(sum(values), 1) if values else None

    return {
        "looms_collected": len(rows),
        "looms_missing": sum(1 for i in items if i.status != "success"),
        "avg_efficiency": round(sum(efficiencies) / len(efficiencies), 2) if efficiencies else None,
        "avg_rpm": round(sum(rpms) / len(rpms), 2) if rpms else None,
        "total_production": round(sum(production), 2) if production else None,
        "total_stops": total("total_stop_ct") or 0,
        "breakdown_known": any(
            r.trama_stops is not None or r.urdume_stops is not None or r.outros_stops is not None
            for r in rows
        ),
        "trama_stops": total("trama_stops"),
        "urdume_stops": total("urdume_stops"),
        "outros_stops": total("outros_stops"),
        "trama_stops_min": total("trama_stops_min"),
        "urdume_stops_min": total("urdume_stops_min"),
        "outros_stops_min": total("outros_stops_min"),
    }


@router.get("")
def daily_status(
    day: Optional[date] = Query(None, description="Data coletada (default: dia anterior)"),
    db: Session = Depends(get_db),
) -> dict:
    """Situacao da coleta diaria: resumo, teares coletados e teares que faltaram."""
    target = day or get_yesterday()
    run = db.execute(
        select(DailyCollectionRun).where(DailyCollectionRun.collection_date == target)
    ).scalar_one_or_none()

    if run is None:
        return {
            "collection_date": target.isoformat(),
            "status": "not_started",
            "total_machines": 0,
            "success_count": 0,
            "failed_count": 0,
            "retry_count": 0,
            "summary": None,
            "items": [],
            "looms": [],
        }

    items = _items_of(db, run.id)
    rows = list(
        db.execute(
            select(DailyLoomData)
            .where(DailyLoomData.collection_date == target)
            .order_by(DailyLoomData.mac_name)
        ).scalars()
    )
    payload = _run_out(run, items)
    payload["summary"] = _summary(run, rows, items)
    payload["looms"] = [
        {
            "mac_name": r.mac_name,
            "source": r.source,
            "shift_id": r.shift_id,
            "style": r.style,
            "production": r.production,
            "efficiency": r.efficiency,
            "rpm": r.rpm,
            "run_time_min": r.run_time_min,
            "stop_time_min": r.stop_time_min,
            "total_stop_ct": r.total_stop_ct,
            "total_stop_tm_min": r.total_stop_tm_min,
            "trama_stops": r.trama_stops,
            "trama_stops_min": r.trama_stops_min,
            "urdume_stops": r.urdume_stops,
            "urdume_stops_min": r.urdume_stops_min,
            "outros_stops": r.outros_stops,
            "outros_stops_min": r.outros_stops_min,
            "collected_at": _iso(r.collected_at),
        }
        for r in rows
    ]
    return payload


@router.get("/history")
def daily_history(limit: int = Query(30, ge=1, le=365), db: Session = Depends(get_db)) -> list[dict]:
    """Ultimas execucoes da coleta diaria."""
    runs = list(
        db.execute(
            select(DailyCollectionRun)
            .order_by(DailyCollectionRun.collection_date.desc())
            .limit(limit)
        ).scalars()
    )
    return [
        {
            "collection_date": r.collection_date.isoformat(),
            "status": r.status,
            "total_machines": r.total_machines,
            "success_count": r.success_count,
            "failed_count": r.failed_count,
            "retry_count": r.retry_count,
            "finished_at": _iso(r.finished_at),
        }
        for r in runs
    ]


@router.post("/collect")
def daily_collect(
    day: Optional[date] = Query(None, description="Data a coletar (default: dia anterior)"),
    force: bool = Query(False, description="Refaz a coleta mesmo se ja concluida"),
    db: Session = Depends(get_db),
    _=Depends(require_roles(UserRole.admin)),
) -> dict:
    """Dispara a coleta do dia anterior (bloqueado se ja executada no dia)."""
    target = day or get_yesterday()
    run = collect_daily_data(db, target, force=force)
    items = _items_of(db, run.id)
    return _run_out(run, items)


@router.post("/retry")
def daily_retry(
    day: Optional[date] = Query(None, description="Data da coleta (default: dia anterior)"),
    db: Session = Depends(get_db),
    _=Depends(require_roles(UserRole.admin)),
) -> dict:
    """Reprocessa a fila de teares que faltaram."""
    target = day or get_yesterday()
    run = retry_pending(db, target, respect_interval=False)
    if run is None:
        raise HTTPException(status_code=404, detail="Nenhuma coleta encontrada para a data")
    items = _items_of(db, run.id)
    return _run_out(run, items)
