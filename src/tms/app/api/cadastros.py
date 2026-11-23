"""API de cadastros TMS 8.0: grupos de teares, membros e operadores."""

from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from tms.app.deps.auth import require_roles
from tms.db.base import get_db
from tms.models.auth import UserRole
from tms.models.daily import DailyLoomData
from tms.models.machine_group import MachineGroup, MachineGroupMember
from tms.models.masters import Machine, Operator
from tms.models.shift_turn import ShiftTurn

router = APIRouter(prefix="/api/cadastros", tags=["cadastros"])

# ---------------------------------------------------------------------------
# Grupos de teares
# ---------------------------------------------------------------------------


@router.get("/grupos", response_model=list[dict])
def list_grupos(
    db: Session = Depends(get_db),
    active_only: bool = Query(False),
    _=Depends(require_roles(UserRole.admin)),
) -> list[dict]:
    stmt = select(MachineGroup).order_by(MachineGroup.name)
    if active_only:
        stmt = stmt.where(MachineGroup.active.is_(True))
    rows = db.execute(stmt).scalars().all()
    return [
        {
            "id": g.id,
            "name": g.name,
            "description": g.description,
            "shift_turn_id": g.shift_turn_id,
            "shift_turn_name": g.shift_turn.name if g.shift_turn else None,
            "active": g.active,
            "created_at": g.created_at.isoformat() if g.created_at else None,
            "updated_at": g.updated_at.isoformat() if g.updated_at else None,
        }
        for g in rows
    ]


@router.get("/grupos/{grupo_id}", response_model=dict)
def get_grupo(
    grupo_id: int,
    db: Session = Depends(get_db),
    _=Depends(require_roles(UserRole.admin)),
) -> dict:
    g = db.get(MachineGroup, grupo_id)
    if g is None:
        raise HTTPException(status_code=404, detail="Grupo não encontrado")
    return {
        "id": g.id,
        "name": g.name,
        "description": g.description,
        "shift_turn_id": g.shift_turn_id,
        "shift_turn_name": g.shift_turn.name if g.shift_turn else None,
        "active": g.active,
    }


@router.post("/grupos", response_model=dict)
def create_grupo(
    payload: dict,
    db: Session = Depends(get_db),
    _=Depends(require_roles(UserRole.admin)),
) -> dict:
    name = (payload.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Nome do grupo é obrigatório")

    existe = db.execute(
        select(MachineGroup).where(MachineGroup.name == name)
    ).scalar_one_or_none()
    if existe:
        raise HTTPException(status_code=409, detail="Grupo já cadastrado")

    g = MachineGroup(
        name=name,
        description=payload.get("description"),
        shift_turn_id=payload.get("shift_turn_id"),
        active=bool(payload.get("active", True)),
    )
    db.add(g)
    db.commit()
    db.refresh(g)
    return {
        "id": g.id,
        "name": g.name,
        "description": g.description,
        "shift_turn_id": g.shift_turn_id,
        "active": g.active,
    }


@router.put("/grupos/{grupo_id}", response_model=dict)
def update_grupo(
    grupo_id: int,
    payload: dict,
    db: Session = Depends(get_db),
    _=Depends(require_roles(UserRole.admin)),
) -> dict:
    g = db.get(MachineGroup, grupo_id)
    if g is None:
        raise HTTPException(status_code=404, detail="Grupo não encontrado")

    if "name" in payload:
        name = payload["name"].strip()
        if name:
            clash = db.execute(
                select(MachineGroup).where(
                    MachineGroup.name == name, MachineGroup.id != grupo_id
                )
            ).scalar_one_or_none()
            if clash:
                raise HTTPException(status_code=409, detail="Nome de grupo já em uso")
            g.name = name

    if "description" in payload:
        g.description = payload["description"]
    if "shift_turn_id" in payload:
        g.shift_turn_id = payload["shift_turn_id"]
    if "active" in payload:
        g.active = bool(payload["active"])

    db.commit()
    db.refresh(g)
    return {
        "id": g.id,
        "name": g.name,
        "description": g.description,
        "shift_turn_id": g.shift_turn_id,
        "active": g.active,
    }


@router.delete("/grupos/{grupo_id}")
def delete_grupo(
    grupo_id: int,
    db: Session = Depends(get_db),
    _=Depends(require_roles(UserRole.admin)),
) -> dict:
    g = db.get(MachineGroup, grupo_id)
    if g is None:
        raise HTTPException(status_code=404, detail="Grupo não encontrado")
    db.delete(g)
    db.commit()
    return {"ok": True}


# ---------------------------------------------------------------------------
# Membros do grupo (teares vinculados)
# ---------------------------------------------------------------------------


@router.get("/grupos/{grupo_id}/membros", response_model=list[dict])
def list_membros(
    grupo_id: int,
    db: Session = Depends(get_db),
    _=Depends(require_roles(UserRole.admin)),
) -> list[dict]:
    g = db.get(MachineGroup, grupo_id)
    if g is None:
        raise HTTPException(status_code=404, detail="Grupo não encontrado")

    membros = db.execute(
        select(MachineGroupMember)
        .where(MachineGroupMember.group_id == grupo_id)
        .order_by(MachineGroupMember.created_at)
    ).scalars().all()

    out = []
    for m in membros:
        mac = db.get(Machine, m.machine_id)
        out.append(
            {
                "id": m.id,
                "group_id": m.group_id,
                "machine_id": m.machine_id,
                "mac_name": mac.mac_name if mac else None,
                "mac_type": mac.mac_type if mac else None,
                "ip_addr": mac.ip_addr if mac else None,
                "active": mac.active if mac else None,
            }
        )
    return out


@router.post("/grupos/{grupo_id}/membros", response_model=dict)
def add_membro(
    grupo_id: int,
    payload: dict,
    db: Session = Depends(get_db),
    _=Depends(require_roles(UserRole.admin)),
) -> dict:
    g = db.get(MachineGroup, grupo_id)
    if g is None:
        raise HTTPException(status_code=404, detail="Grupo não encontrado")

    machine_id = payload.get("machine_id")
    if not machine_id:
        raise HTTPException(status_code=400, detail="machine_id é obrigatório")

    mac = db.get(Machine, machine_id)
    if mac is None:
        raise HTTPException(status_code=404, detail="Tear não encontrado")

    existe = db.execute(
        select(MachineGroupMember).where(
            MachineGroupMember.group_id == grupo_id,
            MachineGroupMember.machine_id == machine_id,
        )
    ).scalar_one_or_none()
    if existe:
        raise HTTPException(status_code=409, detail="Tear já pertence a este grupo")

    m = MachineGroupMember(group_id=grupo_id, machine_id=machine_id)
    db.add(m)
    db.commit()
    db.refresh(m)
    return {
        "id": m.id,
        "group_id": m.group_id,
        "machine_id": m.machine_id,
        "mac_name": mac.mac_name,
    }


@router.delete("/grupos/{grupo_id}/membros/{membro_id}")
def remove_membro(
    grupo_id: int,
    membro_id: int,
    db: Session = Depends(get_db),
    _=Depends(require_roles(UserRole.admin)),
) -> dict:
    m = db.get(MachineGroupMember, membro_id)
    if m is None or m.group_id != grupo_id:
        raise HTTPException(status_code=404, detail="Membro não encontrado")
    db.delete(m)
    db.commit()
    return {"ok": True}


# ---------------------------------------------------------------------------
# Operadores
# ---------------------------------------------------------------------------


@router.get("/operadores", response_model=list[dict])
def list_operadores(
    db: Session = Depends(get_db),
    active_only: bool = Query(False),
    _=Depends(require_roles(UserRole.admin)),
) -> list[dict]:
    stmt = select(Operator).order_by(Operator.name)
    if active_only:
        stmt = stmt.where(Operator.active.is_(True))
    rows = db.execute(stmt).scalars().all()
    out = []
    for o in rows:
        grupo = db.get(MachineGroup, o.group_id) if o.group_id else None
        out.append(
            {
                "id": o.id,
                "code": o.code,
                "name": o.name,
                "role": o.role,
                "shift_day": o.shift_day,
                "group_id": o.group_id,
                "group_name": grupo.name if grupo else None,
                "active": o.active,
            }
        )
    return out


@router.get("/operadores/{operador_id}", response_model=dict)
def get_operador(
    operador_id: int,
    db: Session = Depends(get_db),
    _=Depends(require_roles(UserRole.admin)),
) -> dict:
    o = db.get(Operator, operador_id)
    if o is None:
        raise HTTPException(status_code=404, detail="Operador não encontrado")
    grupo = db.get(MachineGroup, o.group_id) if o.group_id else None
    return {
        "id": o.id,
        "code": o.code,
        "name": o.name,
        "role": o.role,
        "shift_day": o.shift_day,
        "group_id": o.group_id,
        "group_name": grupo.name if grupo else None,
        "active": o.active,
    }


@router.post("/operadores", response_model=dict)
def create_operador(
    payload: dict,
    db: Session = Depends(get_db),
    _=Depends(require_roles(UserRole.admin)),
) -> dict:
    code = (payload.get("code") or "").strip()
    name = (payload.get("name") or "").strip()
    if not code or not name:
        raise HTTPException(status_code=400, detail="Código e nome são obrigatórios")

    existe = db.execute(select(Operator).where(Operator.code == code)).scalar_one_or_none()
    if existe:
        raise HTTPException(status_code=409, detail="Código de operador já cadastrado")

    group_id = payload.get("group_id")
    if group_id is not None:
        grupo = db.get(MachineGroup, group_id)
        if grupo is None:
            raise HTTPException(status_code=404, detail="Grupo não encontrado")

    o = Operator(
        code=code,
        name=name,
        role=payload.get("role", "tecelao"),
        shift_day=payload.get("shift_day"),
        group_id=group_id,
        active=bool(payload.get("active", True)),
    )
    db.add(o)
    db.commit()
    db.refresh(o)
    return {
        "id": o.id,
        "code": o.code,
        "name": o.name,
        "role": o.role,
        "group_id": o.group_id,
        "active": o.active,
    }


@router.put("/operadores/{operador_id}", response_model=dict)
def update_operador(
    operador_id: int,
    payload: dict,
    db: Session = Depends(get_db),
    _=Depends(require_roles(UserRole.admin)),
) -> dict:
    o = db.get(Operator, operador_id)
    if o is None:
        raise HTTPException(status_code=404, detail="Operador não encontrado")

    if "code" in payload:
        code = payload["code"].strip()
        if code:
            clash = db.execute(
                select(Operator).where(
                    Operator.code == code, Operator.id != operador_id
                )
            ).scalar_one_or_none()
            if clash:
                raise HTTPException(status_code=409, detail="Código já em uso")
            o.code = code

    if "name" in payload:
        o.name = payload["name"].strip()
    if "role" in payload:
        o.role = payload["role"]
    if "shift_day" in payload:
        o.shift_day = payload["shift_day"]
    if "group_id" in payload:
        gid = payload["group_id"]
        if gid is not None:
            grupo = db.get(MachineGroup, gid)
            if grupo is None:
                raise HTTPException(status_code=404, detail="Grupo não encontrado")
        o.group_id = gid
    if "active" in payload:
        o.active = bool(payload["active"])

    db.commit()
    db.refresh(o)
    return {
        "id": o.id,
        "code": o.code,
        "name": o.name,
        "role": o.role,
        "group_id": o.group_id,
        "active": o.active,
    }


@router.delete("/operadores/{operador_id}")
def delete_operador(
    operador_id: int,
    db: Session = Depends(get_db),
    _=Depends(require_roles(UserRole.admin)),
) -> dict:
    o = db.get(Operator, operador_id)
    if o is None:
        raise HTTPException(status_code=404, detail="Operador não encontrado")
    db.delete(o)
    db.commit()
    return {"ok": True}


# ---------------------------------------------------------------------------
# Turnos disponíveis para vincular a grupo
# ---------------------------------------------------------------------------


@router.get("/turnos-disponiveis", response_model=list[dict])
def list_turnos_disponiveis(
    db: Session = Depends(get_db),
    _=Depends(require_roles(UserRole.admin)),
) -> list[dict]:
    rows = db.execute(
        select(ShiftTurn).order_by(ShiftTurn.sort_order, ShiftTurn.name)
    ).scalars().all()
    return [
        {
            "id": t.id,
            "name": t.name,
            "start_time": t.start_time,
            "end_time": t.end_time,
            "active": t.active,
            "wraps_midnight": t.wraps_midnight,
        }
        for t in rows
    ]


# ---------------------------------------------------------------------------
# Máquinas (para vincular a grupos)
# ---------------------------------------------------------------------------


@router.get("/maquinas", response_model=list[dict])
def list_maquinas(
    db: Session = Depends(get_db),
    _=Depends(require_roles(UserRole.admin)),
) -> list[dict]:
    rows = db.execute(
        select(Machine).order_by(Machine.mac_name)
    ).scalars().all()
    return [
        {
            "id": m.id,
            "mac_name": m.mac_name,
            "mac_type": m.mac_type,
            "ip_addr": m.ip_addr,
            "active": m.active,
            "is_double": m.is_double,
        }
        for m in rows
    ]


# ---------------------------------------------------------------------------
# Eficiencia por grupo
# ---------------------------------------------------------------------------


@router.get("/grupos/{grupo_id}/eficiencia", response_model=dict)
def eficiencia_por_grupo(
    grupo_id: int,
    db: Session = Depends(get_db),
    day_from: Optional[date] = Query(None, description="Data inicial (YYYY-MM-DD)"),
    day_to: Optional[date] = Query(None, description="Data final (YYYY-MM-DD)"),
    _=Depends(require_roles(UserRole.admin)),
) -> dict:
    """Eficiencia agregada de um grupo de teares.

    Junta daily_loom_data com machine_group_members para filtrar apenas
    os teares que pertencem ao grupo na data da coleta.
    """
    g = db.get(MachineGroup, grupo_id)
    if g is None:
        raise HTTPException(status_code=404, detail="Grupo não encontrado")

    # Maquina_ids do grupo
    membro_ids = db.execute(
        select(MachineGroupMember.machine_id).where(
            MachineGroupMember.group_id == grupo_id
        )
    ).scalars().all()

    if not membro_ids:
        return {
            "grupo": {"id": g.id, "name": g.name},
            "total_teares": 0,
            "coletas": 0,
            "avg_efficiency": None,
            "avg_rpm": None,
            "total_production": None,
            "total_pontos_reais": None,
            "total_metros_reais": None,
            "total_stops": 0,
            "total_run_min": None,
            "total_stop_min": None,
            "por_tear": [],
        }

    stmt = (
        select(
            DailyLoomData.machine_id,
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
        .where(DailyLoomData.machine_id.in_(membro_ids))
        .group_by(DailyLoomData.machine_id)
    )
    if day_from is not None:
        stmt = stmt.where(DailyLoomData.collection_date >= day_from)
    if day_to is not None:
        stmt = stmt.where(DailyLoomData.collection_date <= day_to)

    rows = db.execute(stmt).all()

    por_tear = []
    all_effs = []
    all_rpms = []
    total_prod = 0.0
    total_pontos_reais = 0.0
    total_metros_reais = 0.0
    total_stops = 0
    total_run = 0.0
    total_stop = 0.0
    total_coletas = 0

    for r in rows:
        eff = float(r.avg_efficiency) if r.avg_efficiency is not None else None
        rpm = float(r.avg_rpm) if r.avg_rpm is not None else None
        mac = db.get(Machine, r.machine_id)
        if eff is not None:
            all_effs.append(eff)
        if rpm is not None:
            all_rpms.append(rpm)
        total_coletas += int(r.coletas or 0)
        if r.total_production:
            total_prod += float(r.total_production)
        if r.total_pontos_reais:
            total_pontos_reais += float(r.total_pontos_reais)
        if r.total_metros_reais:
            total_metros_reais += float(r.total_metros_reais)
        if r.total_stops:
            total_stops += int(r.total_stops)
        if r.total_run_min:
            total_run += float(r.total_run_min)
        if r.total_stop_min:
            total_stop += float(r.total_stop_min)

        por_tear.append(
            {
                "machine_id": r.machine_id,
                "mac_name": mac.mac_name if mac else None,
                "coletas": int(r.coletas or 0),
                "avg_efficiency": round(eff, 2) if eff is not None else None,
                "avg_rpm": round(rpm, 2) if rpm is not None else None,
                "total_production": round(float(r.total_production), 2) if r.total_production else None,
                "total_pontos_reais": round(float(r.total_pontos_reais), 2) if r.total_pontos_reais else None,
                "total_metros_reais": round(float(r.total_metros_reais), 2) if r.total_metros_reais else None,
                "total_stops": int(r.total_stops or 0),
            }
        )

    por_tear.sort(key=lambda x: x["mac_name"] or "")

    avg_eff = round(sum(all_effs) / len(all_effs), 2) if all_effs else None
    avg_rpm = round(sum(all_rpms) / len(all_rpms), 2) if all_rpms else None

    return {
        "grupo": {"id": g.id, "name": g.name, "description": g.description},
        "total_teares": len(membro_ids),
        "coletas": total_coletas,
        "avg_efficiency": avg_eff,
        "avg_rpm": avg_rpm,
        "total_production": round(total_prod, 2) if total_prod else None,
        "total_pontos_reais": round(total_pontos_reais, 2) if total_pontos_reais else None,
        "total_metros_reais": round(total_metros_reais, 2) if total_metros_reais else None,
        "total_stops": total_stops,
        "total_run_min": round(total_run, 2) if total_run else None,
        "total_stop_min": round(total_stop, 2) if total_stop else None,
        "por_tear": por_tear,
    }


# ---------------------------------------------------------------------------
# Eficiencia por operador
# ---------------------------------------------------------------------------


@router.get("/operadores/{operador_id}/eficiencia", response_model=dict)
def eficiencia_por_operador(
    operador_id: int,
    db: Session = Depends(get_db),
    day_from: Optional[date] = Query(None, description="Data inicial (YYYY-MM-DD)"),
    day_to: Optional[date] = Query(None, description="Data final (YYYY-MM-DD)"),
    _=Depends(require_roles(UserRole.admin)),
) -> dict:
    """Eficiencia agregada de um operador.

    Junta daily_loom_data com machines e machine_group_members, filtrando
    apenas os teares do grupo vinculado ao operador.
    """
    o = db.get(Operator, operador_id)
    if o is None:
        raise HTTPException(status_code=404, detail="Operador não encontrado")

    # Maquina_ids do grupo vinculado ao operador (se houver)
    membro_ids = []
    if o.group_id:
        membro_ids = db.execute(
            select(MachineGroupMember.machine_id).where(
                MachineGroupMember.group_id == o.group_id
            )
        ).scalars().all()

    if not membro_ids:
        return {
            "operador": {
                "id": o.id,
                "code": o.code,
                "name": o.name,
                "role": o.role,
                "group_name": o.group_name if hasattr(o, "group_name") else None,
            },
            "total_teares": 0,
            "coletas": 0,
            "avg_efficiency": None,
            "avg_rpm": None,
            "total_production": None,
            "total_pontos_reais": None,
            "total_metros_reais": None,
            "total_stops": 0,
            "total_run_min": None,
            "total_stop_min": None,
            "por_tear": [],
        }

    stmt = (
        select(
            DailyLoomData.machine_id,
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
        .where(DailyLoomData.machine_id.in_(membro_ids))
        .group_by(DailyLoomData.machine_id)
    )
    if day_from is not None:
        stmt = stmt.where(DailyLoomData.collection_date >= day_from)
    if day_to is not None:
        stmt = stmt.where(DailyLoomData.collection_date <= day_to)

    rows = db.execute(stmt).all()

    por_tear = []
    all_effs = []
    all_rpms = []
    total_prod = 0.0
    total_pontos_reais = 0.0
    total_metros_reais = 0.0
    total_stops = 0
    total_run = 0.0
    total_stop = 0.0
    total_coletas = 0

    for r in rows:
        eff = float(r.avg_efficiency) if r.avg_efficiency is not None else None
        rpm = float(r.avg_rpm) if r.avg_rpm is not None else None
        mac = db.get(Machine, r.machine_id)
        if eff is not None:
            all_effs.append(eff)
        if rpm is not None:
            all_rpms.append(rpm)
        total_coletas += int(r.coletas or 0)
        if r.total_production:
            total_prod += float(r.total_production)
        if r.total_pontos_reais:
            total_pontos_reais += float(r.total_pontos_reais)
        if r.total_metros_reais:
            total_metros_reais += float(r.total_metros_reais)
        if r.total_stops:
            total_stops += int(r.total_stops)
        if r.total_run_min:
            total_run += float(r.total_run_min)
        if r.total_stop_min:
            total_stop += float(r.total_stop_min)

        por_tear.append(
            {
                "machine_id": r.machine_id,
                "mac_name": mac.mac_name if mac else None,
                "coletas": int(r.coletas or 0),
                "avg_efficiency": round(eff, 2) if eff is not None else None,
                "avg_rpm": round(rpm, 2) if rpm is not None else None,
                "total_production": round(float(r.total_production), 2) if r.total_production else None,
                "total_pontos_reais": round(float(r.total_pontos_reais), 2) if r.total_pontos_reais else None,
                "total_metros_reais": round(float(r.total_metros_reais), 2) if r.total_metros_reais else None,
                "total_stops": int(r.total_stops or 0),
            }
        )

    por_tear.sort(key=lambda x: x["mac_name"] or "")

    avg_eff = round(sum(all_effs) / len(all_effs), 2) if all_effs else None
    avg_rpm = round(sum(all_rpms) / len(all_rpms), 2) if all_rpms else None

    grupo = db.get(MachineGroup, o.group_id) if o.group_id else None

    return {
        "operador": {
            "id": o.id,
            "code": o.code,
            "name": o.name,
            "role": o.role,
            "group_id": o.group_id,
            "group_name": grupo.name if grupo else None,
        },
        "total_teares": len(membro_ids),
        "coletas": total_coletas,
        "avg_efficiency": avg_eff,
        "avg_rpm": avg_rpm,
        "total_production": round(total_prod, 2) if total_prod else None,
        "total_pontos_reais": round(total_pontos_reais, 2) if total_pontos_reais else None,
        "total_metros_reais": round(total_metros_reais, 2) if total_metros_reais else None,
        "total_stops": total_stops,
        "total_run_min": round(total_run, 2) if total_run else None,
        "total_stop_min": round(total_stop, 2) if total_stop else None,
        "por_tear": por_tear,
    }
