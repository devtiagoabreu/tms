"""API TMS 8.0: envio de comandos para teares e edicao de dados do tear."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from tms.app.deps.auth import require_roles
from tms.collector import send_command_to_loom
from tms.db.base import get_db
from tms.models.auth import UserRole
from tms.models.loom_command import LoomCommand
from tms.models.masters import Machine

router = APIRouter(prefix="/api/teares", tags=["teares"])

# ---------------------------------------------------------------------------
# Listar teares com dados atuais
# ---------------------------------------------------------------------------


@router.get("", response_model=list[dict])
def list_teares(
    db: Session = Depends(get_db),
    grupo_id: Optional[int] = Query(None, description="Filtrar por grupo"),
    active_only: bool = Query(False),
    _=Depends(require_roles(UserRole.admin)),
) -> list[dict]:
    """Lista teares com ultimo status ao vivo e grupo."""
    stmt = select(Machine).options(selectinload(Machine.group))
    if grupo_id is not None:
        stmt = stmt.join(Machine.group_members).where(
            Machine.group_members.any(group_id=grupo_id)
        )
    if active_only:
        stmt = stmt.where(Machine.active.is_(True))
    stmt = stmt.order_by(Machine.mac_name)

    rows = db.execute(stmt).scalars().all()
    out = []
    for m in rows:
        grupos = m.group
        grupo = grupos[0] if grupos else None
        out.append(
            {
                "id": m.id,
                "mac_name": m.mac_name,
                "mac_type": m.mac_type,
                "ip_addr": m.ip_addr,
                "active": m.active,
                "is_double": m.is_double,
                "group_id": grupo.id if grupo else None,
                "group_name": grupo.name if grupo else None,
            }
        )
    return out


# ---------------------------------------------------------------------------
# Editar dados cadastrais do tear
# ---------------------------------------------------------------------------


@router.get("/{machine_id}", response_model=dict)
def get_tear(
    machine_id: int,
    db: Session = Depends(get_db),
    _=Depends(require_roles(UserRole.admin)),
) -> dict:
    m = db.get(Machine, machine_id)
    if m is None:
        raise HTTPException(status_code=404, detail="Tear não encontrado")
    grupos = m.group
    grupo = grupos[0] if grupos else None
    return {
        "id": m.id,
        "mac_name": m.mac_name,
        "mac_type": m.mac_type,
        "ip_addr": m.ip_addr,
        "active": m.active,
        "is_double": m.is_double,
        "group_id": grupo.id if grupo else None,
        "group_name": grupo.name if grupo else None,
    }


@router.put("/{machine_id}", response_model=dict)
def update_tear(
    machine_id: int,
    payload: dict,
    db: Session = Depends(get_db),
    _=Depends(require_roles(UserRole.admin)),
) -> dict:
    """Altera dados cadastrais do tear (nome, tipo, IP, grupo, ativo)."""
    m = db.get(Machine, machine_id)
    if m is None:
        raise HTTPException(status_code=404, detail="Tear não encontrado")

    if "mac_name" in payload:
        name = payload["mac_name"].strip()
        if name:
            clash = db.execute(
                select(Machine).where(
                    Machine.mac_name == name, Machine.id != machine_id
                )
            ).scalar_one_or_none()
            if clash:
                raise HTTPException(status_code=409, detail="Nome de tear já em uso")
            m.mac_name = name

    if "mac_type" in payload:
        m.mac_type = payload["mac_type"]
    if "ip_addr" in payload:
        m.ip_addr = payload["ip_addr"] or None
    if "active" in payload:
        m.active = bool(payload["active"])
    if "is_double" in payload:
        m.is_double = bool(payload["is_double"])

    db.commit()
    db.refresh(m)
    return {
        "id": m.id,
        "mac_name": m.mac_name,
        "mac_type": m.mac_type,
        "ip_addr": m.ip_addr,
        "active": m.active,
        "is_double": m.is_double,
    }


# ---------------------------------------------------------------------------
# Enviar comando para tear
# ---------------------------------------------------------------------------


@router.post("/{machine_id}/comandos", response_model=dict)
def send_command(
    machine_id: int,
    payload: dict,
    db: Session = Depends(get_db),
    user=Depends(require_roles(UserRole.admin)),
) -> dict:
    """Envia um comando para o tear (set_style, set_shift, reset_counter, etc.)."""
    m = db.get(Machine, machine_id)
    if m is None:
        raise HTTPException(status_code=404, detail="Tear não encontrado")

    command_type = payload.get("command_type")
    if not command_type:
        raise HTTPException(status_code=400, detail="command_type é obrigatório")

    command_payload = payload.get("payload")

    # Tenta enviar o comando para o tear via HTTP.
    sucesso, erro = send_command_to_loom(
        m.ip_addr or "0.0.0.0",
        command_type,
        command_payload,
        timeout=10.0,
    )

    cmd = LoomCommand(
        machine_id=machine_id,
        command_type=command_type,
        payload=command_payload,
        status="sent" if sucesso else "error",
        sent_at=datetime.utcnow() if sucesso else None,
        error_message=erro,
        created_by=getattr(user, "name", None) or getattr(user, "code", None),
    )
    db.add(cmd)
    db.commit()
    db.refresh(cmd)

    return {
        "id": cmd.id,
        "machine_id": cmd.machine_id,
        "command_type": cmd.command_type,
        "status": cmd.status,
        "error_message": cmd.error_message,
        "created_at": cmd.created_at.isoformat(),
    }


@router.get("/{machine_id}/comandos", response_model=list[dict])
def list_commands(
    machine_id: int,
    db: Session = Depends(get_db),
    _=Depends(require_roles(UserRole.admin)),
) -> list[dict]:
    """Lista comandos enviados para um tear."""
    rows = db.execute(
        select(LoomCommand)
        .where(LoomCommand.machine_id == machine_id)
        .order_by(LoomCommand.created_at.desc())
    ).scalars().all()
    return [
        {
            "id": c.id,
            "command_type": c.command_type,
            "payload": c.payload,
            "status": c.status,
            "sent_at": c.sent_at.isoformat() if c.sent_at else None,
            "acknowledged_at": c.acknowledged_at.isoformat() if c.acknowledged_at else None,
            "error_message": c.error_message,
            "created_by": c.created_by,
            "created_at": c.created_at.isoformat(),
        }
        for c in rows
    ]


@router.get("/comandos", response_model=list[dict])
def list_all_commands(
    db: Session = Depends(get_db),
    status: Optional[str] = Query(None, description="Filtrar por status"),
    _=Depends(require_roles(UserRole.admin)),
) -> list[dict]:
    """Lista todos os comandos de todos os teares."""
    stmt = select(LoomCommand).order_by(LoomCommand.created_at.desc())
    if status:
        stmt = stmt.where(LoomCommand.status == status)
    rows = db.execute(stmt).scalars().all()
    out = []
    for c in rows:
        m = db.get(Machine, c.machine_id)
        out.append(
            {
                "id": c.id,
                "machine_id": c.machine_id,
                "mac_name": m.mac_name if m else None,
                "command_type": c.command_type,
                "payload": c.payload,
                "status": c.status,
                "sent_at": c.sent_at.isoformat() if c.sent_at else None,
                "created_by": c.created_by,
                "created_at": c.created_at.isoformat(),
            }
        )
    return out


@router.post("/comandos/{command_id}/ack", response_model=dict)
def acknowledge_command(
    command_id: int,
    db: Session = Depends(get_db),
    _=Depends(require_roles(UserRole.admin)),
) -> dict:
    """O tear confirma o recebimento de um comando (ack)."""
    cmd = db.get(LoomCommand, command_id)
    if cmd is None:
        raise HTTPException(status_code=404, detail="Comando não encontrado")
    if cmd.status != "sent":
        raise HTTPException(
            status_code=400, detail="Comando não está em status 'sent'"
        )
    cmd.status = "acknowledged"
    cmd.acknowledged_at = datetime.utcnow()
    db.commit()
    db.refresh(cmd)
    return {
        "id": cmd.id,
        "status": cmd.status,
        "acknowledged_at": cmd.acknowledged_at.isoformat(),
    }
