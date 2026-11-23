"""API de menus configuráveis por usuário (TMS 8.0).

Permite cadastrar menus e itens no banco, agrupados por role, e opcionalmente
fazer "fork" dos menus de um role para um usuário específico (menus pessoais).
Inspirado no pdmtextil.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from tms.app.deps.auth import require_user, require_roles
from tms.db.base import get_db
from tms.models.auth import User, UserRole
from tms.models.navigation import Menu, MenuItem

router = APIRouter(prefix="/api/menus", tags=["menus"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class MenuItemOut(BaseModel):
    id: int
    title: str
    url: Optional[str] = None
    icon: Optional[str] = None
    ordem: int
    active: bool

    class Config:
        from_attributes = True


class MenuItemIn(BaseModel):
    title: str
    url: Optional[str] = None
    icon: Optional[str] = None
    ordem: int = 0
    active: bool = True


class MenuOut(BaseModel):
    id: int
    title: str
    icon: Optional[str] = None
    url: Optional[str] = None
    ordem: int
    role: Optional[str] = None
    active: bool
    items: list[MenuItemOut] = []

    class Config:
        from_attributes = True


class MenuIn(BaseModel):
    title: str
    icon: Optional[str] = None
    url: Optional[str] = None
    ordem: int = 0
    role: Optional[str] = None
    active: bool = True


class MenuReorder(BaseModel):
    menu_ids: list[int]


class MenuItemReorder(BaseModel):
    menu_id: int
    item_ids: list[int]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _user_menus_query(db: Session, usuario_id: int):
    """Retorna menus visíveis para o usuário: globais (sem role) + por role
    do usuário + pessoais (usuario_id)."""
    user = db.get(User, usuario_id)
    if user is None:
        return []

    stmt = (
        select(Menu)
        .options(selectinload(Menu.items))
        .where(
            Menu.active.is_(True),
            (
                (Menu.usuario_id.is_(None) & Menu.role.is_(None))  # global
                | (Menu.role == user.role.value)  # por role
                | (Menu.usuario_id == usuario_id)  # pessoal
            ),
        )
        .order_by(Menu.ordem, Menu.title)
    )
    return db.execute(stmt).scalars().all()


def _menu_tree(menus: list[Menu]) -> list[dict]:
    """Converte lista de Menu em árvore de dicionários para o frontend."""
    out = []
    for m in menus:
        items = sorted(m.items, key=lambda i: (i.ordem, i.title))
        out.append(
            {
                "id": m.id,
                "title": m.title,
                "icon": m.icon,
                "url": m.url,
                "ordem": m.ordem,
                "role": m.role,
                "active": m.active,
                "items": [
                    {
                        "id": i.id,
                        "title": i.title,
                        "url": i.url,
                        "icon": i.icon,
                        "ordem": i.ordem,
                        "active": i.active,
                    }
                    for i in items
                ],
            }
        )
    return out


# ---------------------------------------------------------------------------
# Endpoints públicos (menu do usuário logado)
# ---------------------------------------------------------------------------


@router.get("/me", response_model=list[MenuOut])
def list_my_menus(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_user),
) -> list[MenuOut]:
    """Retorna os menus visíveis para o usuário logado (mesclados por role +
    menus pessoais)."""
    menus = _user_menus_query(db, current_user.id)
    return [MenuOut.model_validate(m) for m in menus]


# ---------------------------------------------------------------------------
# Endpoints admin (configuração completa)
# ---------------------------------------------------------------------------


@router.get("", response_model=list[MenuOut])
def list_menus_admin(
    db: Session = Depends(get_db),
    _=Depends(require_roles(UserRole.admin)),
) -> list[MenuOut]:
    """Lista todos os menus (admin) para configuração."""
    menus = (
        db.execute(select(Menu).options(selectinload(Menu.items)).order_by(Menu.ordem, Menu.title))
        .scalars()
        .all()
    )
    return [MenuOut.model_validate(m) for m in menus]


@router.post("", response_model=MenuOut)
def create_menu(
    payload: MenuIn,
    db: Session = Depends(get_db),
    _=Depends(require_roles(UserRole.admin)),
) -> MenuOut:
    """Cria um novo menu."""
    m = Menu(
        title=payload.title,
        icon=payload.icon,
        url=payload.url,
        ordem=payload.ordem,
        role=payload.role,
        active=payload.active,
    )
    db.add(m)
    db.commit()
    db.refresh(m)
    return MenuOut.model_validate(m)


@router.get("/{menu_id}", response_model=MenuOut)
def get_menu(
    menu_id: int,
    db: Session = Depends(get_db),
    _=Depends(require_roles(UserRole.admin)),
) -> MenuOut:
    m = db.get(Menu, menu_id)
    if m is None:
        raise HTTPException(status_code=404, detail="Menu não encontrado")
    return MenuOut.model_validate(m)


@router.put("/{menu_id}", response_model=MenuOut)
def update_menu(
    menu_id: int,
    payload: MenuIn,
    db: Session = Depends(get_db),
    _=Depends(require_roles(UserRole.admin)),
) -> MenuOut:
    m = db.get(Menu, menu_id)
    if m is None:
        raise HTTPException(status_code=404, detail="Menu não encontrado")

    m.title = payload.title
    m.icon = payload.icon
    m.url = payload.url
    m.ordem = payload.ordem
    m.role = payload.role
    m.active = payload.active

    db.commit()
    db.refresh(m)
    return MenuOut.model_validate(m)


@router.delete("/{menu_id}")
def delete_menu(
    menu_id: int,
    db: Session = Depends(get_db),
    _=Depends(require_roles(UserRole.admin)),
) -> dict:
    m = db.get(Menu, menu_id)
    if m is None:
        raise HTTPException(status_code=404, detail="Menu não encontrado")
    db.delete(m)
    db.commit()
    return {"ok": True}


# ---------------------------------------------------------------------------
# Itens de menu
# ---------------------------------------------------------------------------


@router.post("/{menu_id}/itens", response_model=MenuItemOut)
def create_menu_item(
    menu_id: int,
    payload: MenuItemIn,
    db: Session = Depends(get_db),
    _=Depends(require_roles(UserRole.admin)),
) -> MenuItemOut:
    m = db.get(Menu, menu_id)
    if m is None:
        raise HTTPException(status_code=404, detail="Menu não encontrado")

    item = MenuItem(
        menu_id=menu_id,
        title=payload.title,
        url=payload.url,
        icon=payload.icon,
        ordem=payload.ordem,
        active=payload.active,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return MenuItemOut.model_validate(item)


@router.put("/itens/{item_id}", response_model=MenuItemOut)
def update_menu_item(
    item_id: int,
    payload: MenuItemIn,
    db: Session = Depends(get_db),
    _=Depends(require_roles(UserRole.admin)),
) -> MenuItemOut:
    item = db.get(MenuItem, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Item de menu não encontrado")

    item.title = payload.title
    item.url = payload.url
    item.icon = payload.icon
    item.ordem = payload.ordem
    item.active = payload.active

    db.commit()
    db.refresh(item)
    return MenuItemOut.model_validate(item)


@router.delete("/itens/{item_id}")
def delete_menu_item(
    item_id: int,
    db: Session = Depends(get_db),
    _=Depends(require_roles(UserRole.admin)),
) -> dict:
    item = db.get(MenuItem, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Item de menu não encontrado")
    db.delete(item)
    db.commit()
    return {"ok": True}


# ---------------------------------------------------------------------------
# Ordenação
# ---------------------------------------------------------------------------


@router.post("/ordenar")
def reorder_menus(
    payload: MenuReorder,
    db: Session = Depends(get_db),
    _=Depends(require_roles(UserRole.admin)),
) -> dict:
    """Reordena os menus principais."""
    for idx, menu_id in enumerate(payload.menu_ids):
        m = db.get(Menu, menu_id)
        if m is not None:
            m.ordem = idx
    db.commit()
    return {"ok": True}


@router.post("/itens/ordenar")
def reorder_menu_items(
    payload: MenuItemReorder,
    db: Session = Depends(get_db),
    _=Depends(require_roles(UserRole.admin)),
) -> dict:
    """Reordena os itens dentro de um menu."""
    for idx, item_id in enumerate(payload.item_ids):
        item = db.get(MenuItem, item_id)
        if item is not None and item.menu_id == payload.menu_id:
            item.ordem = idx
    db.commit()
    return {"ok": True}
