"""CRUD de turnos de producao (cadastro, edicao, ativo/inativo) e eficiencia."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from tms.db.base import get_db
from tms.models.daily import DailyLoomData
from tms.models.shift_turn import ShiftTurn

router = APIRouter(prefix="/api/shift-turns", tags=["shift-turns"])

# Mascara de bits para dias da semana: bit0=domingo ... bit6=snado
DAYS_OF_WEEK = [
    ("domingo", 1),
    ("segunda", 2),
    ("terca", 4),
    ("quarta", 8),
    ("quinta", 16),
    ("sexta", 32),
    ("snado", 64),
]


def _mask_to_days(mask: int) -> list[str]:
    return [name for name, bit in DAYS_OF_WEEK if mask & bit]


def _days_to_mask(days: list[str]) -> int:
    mask = 0
    day_to_bit = {name: bit for name, bit in DAYS_OF_WEEK}
    for d in days:
        mask |= day_to_bit.get(d, 0)
    return mask


@router.get("")
def list_shift_turns(
    db: Session = Depends(get_db),
    active_only: bool = Query(False, description="Somente turnos ativos"),
) -> list[dict]:
    """Lista todos os turnos cadastrados."""
    stmt = select(ShiftTurn).order_by(ShiftTurn.sort_order, ShiftTurn.name)
    if active_only:
        stmt = stmt.where(ShiftTurn.active.is_(True))
    rows = db.execute(stmt).scalars().all()
    return [
        {
            "id": r.id,
            "name": r.name,
            "start_time": r.start_time,
            "end_time": r.end_time,
            "active": r.active,
            "days": _mask_to_days(r.days_mask),
            "days_mask": r.days_mask,
            "wraps_midnight": r.wraps_midnight,
            "sort_order": r.sort_order,
        }
        for r in rows
    ]


@router.get("/eficiencia")
def eficiencia_por_turno(
    db: Session = Depends(get_db),
    day_from: Optional[date] = Query(None, description="Data inicial (YYYY-MM-DD)"),
    day_to: Optional[date] = Query(None, description="Data final (YYYY-MM-DD)"),
) -> list[dict]:
    """Eficiencia agregada por turno cadastrado.

    Agrupa ``daily_loom_data`` por ``shift_turn_id`` e calcula:
    media de eficiencia, RPM, producao, paradas e tempo de parada.
    Apenas turnos que possuem pelo menos uma coleta vinculada aparecem.
    """
    stmt = (
        select(
            ShiftTurn.id,
            ShiftTurn.name,
            ShiftTurn.start_time,
            ShiftTurn.end_time,
            func.count(DailyLoomData.id).label("coletas"),
            func.avg(DailyLoomData.efficiency).label("avg_efficiency"),
            func.avg(DailyLoomData.rpm).label("avg_rpm"),
            func.sum(DailyLoomData.production).label("total_production"),
            func.sum(DailyLoomData.pontos_reais).label("total_pontos_reais"),
            func.sum(DailyLoomData.metros_reais).label("total_metros_reais"),
            func.sum(DailyLoomData.total_stop_ct).label("total_stops"),
            func.sum(DailyLoomData.run_time_min).label("total_run_min"),
            func.sum(DailyLoomData.stop_time_min).label("total_stop_min"),
        )
        .join(
            DailyLoomData,
            DailyLoomData.shift_turn_id == ShiftTurn.id,
            isouter=True,
        )
        .group_by(
            ShiftTurn.id,
            ShiftTurn.name,
            ShiftTurn.start_time,
            ShiftTurn.end_time,
        )
        .order_by(ShiftTurn.sort_order, ShiftTurn.name)
    )

    if day_from is not None:
        stmt = stmt.where(DailyLoomData.collection_date >= day_from)
    if day_to is not None:
        stmt = stmt.where(DailyLoomData.collection_date <= day_to)

    rows = db.execute(stmt).all()
    out = []
    for r in rows:
        avg_eff = float(r.avg_efficiency) if r.avg_efficiency is not None else None
        out.append(
            {
                "id": r.id,
                "name": r.name,
                "start_time": r.start_time,
                "end_time": r.end_time,
                "coletas": int(r.coletas or 0),
                "avg_efficiency": round(avg_eff, 2) if avg_eff is not None else None,
                "avg_rpm": round(float(r.avg_rpm), 2) if r.avg_rpm is not None else None,
                "total_production": round(float(r.total_production), 2) if r.total_production is not None else None,
                "total_pontos_reais": round(float(r.total_pontos_reais), 2) if r.total_pontos_reais is not None else None,
                "total_metros_reais": round(float(r.total_metros_reais), 2) if r.total_metros_reais is not None else None,
                "total_stops": int(r.total_stops or 0),
                "total_run_min": round(float(r.total_run_min), 2) if r.total_run_min is not None else None,
                "total_stop_min": round(float(r.total_stop_min), 2) if r.total_stop_min is not None else None,
            }
        )
    return out


@router.get("/{turn_id}")
def get_shift_turn(
    turn_id: int,
    db: Session = Depends(get_db),
) -> dict:
    """Retorna um turno pelo ID."""
    row = db.get(ShiftTurn, turn_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Turno nao encontrado")
    return {
        "id": row.id,
        "name": row.name,
        "start_time": row.start_time,
        "end_time": row.end_time,
        "active": row.active,
        "days": _mask_to_days(row.days_mask),
        "days_mask": row.days_mask,
        "wraps_midnight": row.wraps_midnight,
        "sort_order": row.sort_order,
    }


@router.post("")
def create_shift_turn(
    payload: dict,
    db: Session = Depends(get_db),
) -> dict:
    """Cria um novo turno."""
    name = payload.get("name", "").strip().upper()
    if not name:
        raise HTTPException(status_code=400, detail="Nome do turno e obrigatorio")
    start = payload.get("start_time", "").strip()
    end = payload.get("end_time", "").strip()
    if not start or not end:
        raise HTTPException(status_code=400, detail="Hora de inicio e fim sao obrigatorias")

    existente = db.execute(
        select(ShiftTurn).where(ShiftTurn.name == name)
    ).scalar_one_or_none()
    if existente:
        raise HTTPException(status_code=409, detail="Turno ja cadastrado")

    days = payload.get("days", [])
    days_mask = _days_to_mask(days)

    max_order = db.execute(
        select(ShiftTurn.sort_order).order_by(ShiftTurn.sort_order.desc())
    ).scalar_one_or_none()
    next_order = (max_order or 0) + 1

    row = ShiftTurn(
        name=name,
        start_time=start,
        end_time=end,
        active=bool(payload.get("active", True)),
        days_mask=days_mask,
        wraps_midnight=bool(payload.get("wraps_midnight", False)),
        sort_order=next_order,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return {
        "id": row.id,
        "name": row.name,
        "start_time": row.start_time,
        "end_time": row.end_time,
        "active": row.active,
        "days": _mask_to_days(row.days_mask),
        "days_mask": row.days_mask,
        "wraps_midnight": row.wraps_midnight,
        "sort_order": row.sort_order,
    }


@router.put("/{turn_id}")
def update_shift_turn(
    turn_id: int,
    payload: dict,
    db: Session = Depends(get_db),
) -> dict:
    """Atualiza um turno existente."""
    row = db.get(ShiftTurn, turn_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Turno nao encontrado")

    if "name" in payload:
        name = payload["name"].strip().upper()
        if name:
            clash = db.execute(
                select(ShiftTurn).where(
                    ShiftTurn.name == name, ShiftTurn.id != turn_id
                )
            ).scalar_one_or_none()
            if clash:
                raise HTTPException(status_code=409, detail="Nome de turno ja em uso")
            row.name = name

    if "start_time" in payload:
        row.start_time = payload["start_time"].strip()
    if "end_time" in payload:
        row.end_time = payload["end_time"].strip()
    if "active" in payload:
        row.active = bool(payload["active"])
    if "days" in payload:
        row.days_mask = _days_to_mask(payload["days"])
    if "wraps_midnight" in payload:
        row.wraps_midnight = bool(payload["wraps_midnight"])
    if "sort_order" in payload:
        row.sort_order = int(payload["sort_order"])

    db.commit()
    db.refresh(row)
    return {
        "id": row.id,
        "name": row.name,
        "start_time": row.start_time,
        "end_time": row.end_time,
        "active": row.active,
        "days": _mask_to_days(row.days_mask),
        "days_mask": row.days_mask,
        "wraps_midnight": row.wraps_midnight,
        "sort_order": row.sort_order,
    }


@router.delete("/{turn_id}")
def delete_shift_turn(
    turn_id: int,
    db: Session = Depends(get_db),
) -> dict:
    """Exclui um turno."""
    row = db.get(ShiftTurn, turn_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Turno nao encontrado")
    db.delete(row)
    db.commit()
    return {"ok": True}
