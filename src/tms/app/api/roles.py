"""API de Roles e Permissões (TMS 8.0).

Permite ao administrador configurar quais permissões cada role possui.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from tms.app.deps.auth import require_roles
from tms.db.base import get_db
from tms.models.auth import UserRole
from tms.models.permission import Permission, RolePermission

router = APIRouter(prefix="/api/roles", tags=["roles"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class PermissionOut(BaseModel):
    id: int
    chave: str
    descricao: Optional[str] = None
    modulo: Optional[str] = None
    active: bool

    class Config:
        from_attributes = True


class RolePermissionOut(BaseModel):
    permission_id: int
    chave: str
    descricao: Optional[str] = None
    modulo: Optional[str] = None
    active: bool

    class Config:
        from_attributes = True


class RolePermissionsOut(BaseModel):
    role: str
    permissions: list[RolePermissionOut] = []


class RolePermissionToggle(BaseModel):
    permission_id: int
    active: bool


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/permissoes", response_model=list[PermissionOut])
def list_permissoes(
    db: Session = Depends(get_db),
    _=Depends(require_roles(UserRole.admin)),
) -> list[PermissionOut]:
    """Lista todas as permissões disponíveis."""
    rows = db.execute(
        select(Permission).order_by(Permission.modulo, Permission.chave)
    ).scalars().all()
    return [PermissionOut.model_validate(p) for p in rows]


@router.get("/{role}", response_model=RolePermissionsOut)
def get_role_permissions(
    role: str,
    db: Session = Depends(get_db),
    _=Depends(require_roles(UserRole.admin)),
) -> RolePermissionsOut:
    """Retorna todas as permissões de uma role com status ativo/inativo."""
    if role not in ("admin", "operador", "visualizador"):
        raise HTTPException(status_code=400, detail="Role inválida")

    # Todas as permissões
    todas = db.execute(select(Permission)).scalars().all()
    permissao_map = {p.id: p for p in todas}

    # Permissões ativas para esta role
    rps = db.execute(
        select(RolePermission).where(RolePermission.role == role)
    ).scalars().all()
    rp_map = {rp.permission_id: rp for rp in rps}

    permissoes_out = []
    for p in todas:
        rp = rp_map.get(p.id)
        permissoes_out.append(
            RolePermissionOut(
                permission_id=p.id,
                chave=p.chave,
                descricao=p.descricao,
                modulo=p.modulo,
                active=rp.active if rp else False,
            )
        )

    return RolePermissionsOut(role=role, permissions=permissoes_out)


@router.post("/{role}/permissoes")
def toggle_role_permission(
    role: str,
    payload: RolePermissionToggle,
    db: Session = Depends(get_db),
    _=Depends(require_roles(UserRole.admin)),
) -> dict:
    """Ativa ou desativa uma permissão para uma role."""
    if role not in ("admin", "operador", "visualizador"):
        raise HTTPException(status_code=400, detail="Role inválida")

    perm = db.get(Permission, payload.permission_id)
    if perm is None:
        raise HTTPException(status_code=404, detail="Permissão não encontrada")

    rp = db.execute(
        select(RolePermission).where(
            RolePermission.role == role,
            RolePermission.permission_id == payload.permission_id,
        )
    ).scalar_one_or_none()

    if rp is None:
        rp = RolePermission(
            role=role,
            permission_id=payload.permission_id,
            active=payload.active,
        )
        db.add(rp)
    else:
        rp.active = payload.active

    db.commit()
    return {"ok": True, "role": role, "permission_id": payload.permission_id, "active": payload.active}
