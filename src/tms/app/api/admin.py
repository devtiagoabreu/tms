"""Endpoints administrativos: menus dinâmicos, notificações e configuração.

Inspirado no pdmtextil (menus por role, notificações com regras, config chave/valor).
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from tms.app.deps.auth import CurrentUser, DbSession, require_roles
from tms.models.auth import User, UserRole
from tms.models.masters import Machine
from tms.models.navigation import Menu, MenuItem
from tms.models.notification import Notification, NotificationRule
from tms.models.system_config import SystemConfig

router = APIRouter(prefix="/api/admin", tags=["admin"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_USER_ROLE_VALUES = {r.value for r in UserRole}


def _user_role_value(user: User) -> str:
    return user.role.value if isinstance(user.role, UserRole) else str(user.role)


def _roles_match_rule(user_role: str, roles_json: str) -> bool:
    try:
        roles = json.loads(roles_json)
    except (json.JSONDecodeError, TypeError):
        return False
    return user_role in roles


def _commit(db: Session) -> None:
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise


# ---------------------------------------------------------------------------
# Menus
# ---------------------------------------------------------------------------

@router.get("/menus")
def admin_menus(
    current_user: CurrentUser,
    db: DbSession,
) -> list[dict]:
    """Devolve os menus do usuário logado.

    Regras (inspirado no pdmtextil):
    - Menus globais (usuario_id IS NULL) valem se o role do user bate com o
      campo role, ou se role for None (visível para todos).
    - Menus pessoais (usuario_id == id do user) sempre valem.
    """
    user_role = _user_role_value(current_user)
    uid = current_user.id

    rows = (
        db.execute(
            select(Menu)
            .where(Menu.active.is_(True))
            .where(
                (Menu.usuario_id.is_(None))
                | (Menu.usuario_id == uid)
            )
            .order_by(Menu.ordem, Menu.title)
        )
        .scalars()
        .all()
    )

    out: list[dict] = []
    for m in rows:
        if m.usuario_id is None and m.role is not None and m.role != user_role:
            continue
        items = [
            {
                "id": i.id,
                "title": i.title,
                "url": i.url,
                "icon": i.icon,
                "ordem": i.ordem,
                "active": i.active,
            }
            for i in sorted(m.items, key=lambda x: (x.ordem, x.title))
            if i.active
        ]
        out.append(
            {
                "id": m.id,
                "title": m.title,
                "icon": m.icon,
                "url": m.url,
                "ordem": m.ordem,
                "role": m.role,
                "usuario_id": m.usuario_id,
                "active": m.active,
                "items": items,
                "is_personal": m.usuario_id is not None,
            }
        )
    return out


@router.post("/menus", status_code=status.HTTP_201_CREATED)
def admin_menus_create(
    payload: dict,
    current_user: CurrentUser,
    db: DbSession,
    _=Depends(require_roles(UserRole.admin)),
) -> dict:
    """Cria um menu (apenas admin)."""
    title = (payload.get("title") or "").strip()
    if not title:
        raise HTTPException(status_code=400, detail="title é obrigatório")
    menu = Menu(
        title=title,
        icon=payload.get("icon"),
        url=payload.get("url"),
        ordem=int(payload.get("ordem") or 0),
        role=payload.get("role"),
        usuario_id=payload.get("usuario_id"),
        active=bool(payload.get("active", True)),
    )
    db.add(menu)
    _commit(db)
    return {"id": menu.id, "title": menu.title}


@router.put("/menus/{menu_id}")
def admin_menus_update(
    menu_id: int,
    payload: dict,
    current_user: CurrentUser,
    db: DbSession,
    _=Depends(require_roles(UserRole.admin)),
) -> dict:
    menu = db.get(Menu, menu_id)
    if not menu:
        raise HTTPException(status_code=404, detail="Menu não encontrado")
    for field in ("title", "icon", "url", "role", "active"):
        if field in payload:
            setattr(menu, field, payload[field])
    if "ordem" in payload:
        menu.ordem = int(payload["ordem"])
    _commit(db)
    return {"id": menu.id, "title": menu.title}


@router.delete("/menus/{menu_id}", status_code=status.HTTP_204_NO_CONTENT)
def admin_menus_delete(
    menu_id: int,
    current_user: CurrentUser,
    db: DbSession,
    _=Depends(require_roles(UserRole.admin)),
):
    menu = db.get(Menu, menu_id)
    if not menu:
        raise HTTPException(status_code=404, detail="Menu não encontrado")
    db.delete(menu)
    _commit(db)


@router.post("/menus/{menu_id}/items", status_code=status.HTTP_201_CREATED)
def admin_menu_items_create(
    menu_id: int,
    payload: dict,
    current_user: CurrentUser,
    db: DbSession,
    _=Depends(require_roles(UserRole.admin)),
) -> dict:
    menu = db.get(Menu, menu_id)
    if not menu:
        raise HTTPException(status_code=404, detail="Menu não encontrado")
    title = (payload.get("title") or "").strip()
    if not title:
        raise HTTPException(status_code=400, detail="title é obrigatório")
    item = MenuItem(
        menu_id=menu_id,
        title=title,
        url=payload.get("url"),
        icon=payload.get("icon"),
        ordem=int(payload.get("ordem") or 0),
        active=bool(payload.get("active", True)),
    )
    db.add(item)
    _commit(db)
    return {"id": item.id, "title": item.title}


@router.put("/menus/items/{item_id}")
def admin_menu_items_update(
    item_id: int,
    payload: dict,
    current_user: CurrentUser,
    db: DbSession,
    _=Depends(require_roles(UserRole.admin)),
) -> dict:
    item = db.get(MenuItem, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item não encontrado")
    for field in ("title", "url", "icon", "active"):
        if field in payload:
            setattr(item, field, payload[field])
    if "ordem" in payload:
        item.ordem = int(payload["ordem"])
    _commit(db)
    return {"id": item.id, "title": item.title}


@router.delete("/menus/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def admin_menu_items_delete(
    item_id: int,
    current_user: CurrentUser,
    db: DbSession,
    _=Depends(require_roles(UserRole.admin)),
):
    item = db.get(MenuItem, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item não encontrado")
    db.delete(item)
    _commit(db)


# ---------------------------------------------------------------------------
# Notificações
# ---------------------------------------------------------------------------

@router.get("/notifications")
def admin_notifications(
    current_user: CurrentUser,
    db: DbSession,
    unread_only: bool = Query(False, description="Somente não lidas"),
    limit: int = Query(50, ge=1, le=200),
) -> list[dict]:
    """Lista notificações do usuário logado."""
    stmt = select(Notification).where(Notification.usuario_id == current_user.id)
    if unread_only:
        stmt = stmt.where(Notification.lida.is_(False))
    stmt = stmt.order_by(Notification.criada_em.desc()).limit(limit)
    rows = db.execute(stmt).scalars().all()
    return [
        {
            "id": n.id,
            "tipo": n.tipo,
            "mensagem": n.mensagem,
            "link": n.link,
            "lida": n.lida,
            "criada_em": n.criada_em.isoformat() if n.criada_em else None,
            "lida_em": n.lida_em.isoformat() if n.lida_em else None,
        }
        for n in rows
    ]


@router.get("/notifications/unread-count")
def admin_notifications_unread_count(
    current_user: CurrentUser,
    db: DbSession,
) -> dict:
    """Conta notificações não lidas (badge da navbar)."""
    count = (
        db.execute(
            select(Notification).where(
                Notification.usuario_id == current_user.id,
                Notification.lida.is_(False),
            )
        ).scalar()
        or 0
    )
    return {"unread_count": count}


@router.post("/notifications/{notification_id}/read")
def admin_notifications_read(
    notification_id: int,
    current_user: CurrentUser,
    db: DbSession,
) -> dict:
    """Marca uma notificação como lida."""
    n = db.get(Notification, notification_id)
    if not n or n.usuario_id != current_user.id:
        raise HTTPException(status_code=404, detail="Notificação não encontrada")
    if not n.lida:
        n.lida = True
        n.lida_em = datetime.utcnow()
        _commit(db)
    return {"id": n.id, "lida": True}


@router.post("/notifications/read-all")
def admin_notifications_read_all(
    current_user: CurrentUser,
    db: DbSession,
) -> dict:
    """Marca todas as notificações do usuário como lidas."""
    rows = db.execute(
        select(Notification).where(
            Notification.usuario_id == current_user.id,
            Notification.lida.is_(False),
        )
    ).scalars().all()
    now = datetime.utcnow()
    for n in rows:
        n.lida = True
        n.lida_em = now
    _commit(db)
    return {"updated": len(rows)}


@router.get("/machines")
def admin_machines(
    current_user: CurrentUser,
    db: DbSession,
) -> list[dict]:
    """Lista todas as máquinas com flag de tear duplo."""
    rows = db.execute(select(Machine).order_by(Machine.mac_name)).scalars().all()
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


@router.patch("/machines/{machine_id}/double")
def admin_machine_toggle_double(
    machine_id: int,
    payload: dict,
    current_user: CurrentUser,
    db: DbSession,
    _=Depends(require_roles(UserRole.admin)),
) -> dict:
    """Marca/desmarca um tear como duplo (produz 2 rolos de uma vez)."""
    machine = db.get(Machine, machine_id)
    if not machine:
        raise HTTPException(status_code=404, detail="Tear não encontrado")
    machine.is_double = bool(payload.get("is_double", True))
    _commit(db)
    return {
        "id": machine.id,
        "mac_name": machine.mac_name,
        "is_double": machine.is_double,
    }


@router.post("/notifications/rules", status_code=status.HTTP_201_CREATED)
def admin_notification_rules_create(
    payload: dict,
    current_user: CurrentUser,
    db: DbSession,
    _=Depends(require_roles(UserRole.admin)),
) -> dict:
    """Cadastra/atualiza uma regra de notificação por tipo e roles."""
    tipo = (payload.get("tipo") or "").strip()
    roles = payload.get("roles") or []
    if not tipo:
        raise HTTPException(status_code=400, detail="tipo é obrigatório")
    if not isinstance(roles, list) or not roles:
        raise HTTPException(status_code=400, detail="roles é obrigatório")
    for r in roles:
        if r not in _USER_ROLE_VALUES:
            raise HTTPException(status_code=400, detail=f"role inválido: {r}")
    roles_json = json.dumps(roles, ensure_ascii=False)
    existing = db.execute(
        select(NotificationRule).where(NotificationRule.tipo == tipo)
    ).scalar_one_or_none()
    if existing:
        existing.roles_json = roles_json
        existing.ativo = bool(payload.get("ativo", True))
        _commit(db)
        return {"tipo": existing.tipo, "roles": roles}
    rule = NotificationRule(tipo=tipo, roles_json=roles_json, ativo=True)
    db.add(rule)
    _commit(db)
    return {"tipo": rule.tipo, "roles": roles}


def _notify_users(
    db: Session,
    tipo: str,
    mensagem: str,
    link: Optional[str] = None,
    roles: Optional[list[str]] = None,
    usuario_nome: Optional[str] = None,
) -> int:
    """Cria notificações para os roles da regra (ou roles informados)."""
    if roles is None:
        rule = db.execute(
            select(NotificationRule).where(
                NotificationRule.tipo == tipo,
                NotificationRule.ativo.is_(True),
            )
        ).scalar_one_or_none()
        if not rule:
            return 0
        try:
            roles = json.loads(rule.roles_json)
        except (json.JSONDecodeError, TypeError):
            return 0
    if not roles:
        return 0
    users = db.execute(
        select(User).where(User.is_active.is_(True), User.role.in_(roles))
    ).scalars().all()
    now = datetime.utcnow()
    for u in users:
        db.add(
            Notification(
                tipo=tipo,
                mensagem=mensagem,
                link=link,
                usuario_id=u.id,
                lida=False,
                criada_em=now,
            )
        )
    _commit(db)
    return len(users)


@router.post("/notifications/broadcast", status_code=status.HTTP_201_CREATED)
def admin_notifications_broadcast(
    payload: dict,
    current_user: CurrentUser,
    db: DbSession,
    _=Depends(require_roles(UserRole.admin)),
) -> dict:
    """Dispara uma notificação para os roles de uma regra (admin)."""
    tipo = (payload.get("tipo") or "").strip()
    mensagem = (payload.get("mensagem") or "").strip()
    link = payload.get("link")
    if not tipo or not mensagem:
        raise HTTPException(status_code=400, detail="tipo e mensagem são obrigatórios")
    qtd = _notify_users(db, tipo, mensagem, link, usuario_nome=current_user.full_name)
    return {"tipo": tipo, "usuarios_notificados": qtd}


# ---------------------------------------------------------------------------
# Configuração do sistema
# ---------------------------------------------------------------------------

@router.get("/config")
def admin_config(
    current_user: CurrentUser,
    db: DbSession,
    categoria: Optional[str] = Query(None, description="Filtrar por categoria"),
) -> list[dict]:
    """Lista configurações do sistema."""
    stmt = select(SystemConfig)
    if categoria:
        stmt = stmt.where(SystemConfig.categoria == categoria)
    rows = db.execute(
        stmt.order_by(SystemConfig.categoria, SystemConfig.chave)
    ).scalars().all()
    return [
        {
            "id": c.id,
            "categoria": c.categoria,
            "chave": c.chave,
            "valor": c.valor,
            "tipo": c.tipo,
            "descricao": c.descricao,
            "updated_at": c.updated_at.isoformat() if c.updated_at else None,
        }
        for c in rows
    ]


@router.post("/config", status_code=status.HTTP_201_CREATED)
def admin_config_upsert(
    payload: dict,
    current_user: CurrentUser,
    db: DbSession,
    _=Depends(require_roles(UserRole.admin)),
) -> dict:
    """Cria ou atualiza uma configuração (chave/valor por categoria)."""
    categoria = (payload.get("categoria") or "").strip()
    chave = (payload.get("chave") or "").strip()
    valor = payload.get("valor")
    tipo = payload.get("tipo") or "text"
    descricao = payload.get("descricao")
    if not categoria or not chave:
        raise HTTPException(status_code=400, detail="categoria e chave são obrigatórios")
    if tipo not in ("text", "number", "boolean", "json"):
        raise HTTPException(status_code=400, detail="tipo inválido")
    valor_str = (
        json.dumps(valor, ensure_ascii=False)
        if tipo == "json" and valor is not None
        else (str(valor) if valor is not None else None)
    )
    existing = db.execute(
        select(SystemConfig).where(
            SystemConfig.categoria == categoria,
            SystemConfig.chave == chave,
        )
    ).scalar_one_or_none()
    if existing:
        existing.valor = valor_str
        existing.tipo = tipo
        existing.descricao = descricao
        existing.updated_at = datetime.utcnow()
        _commit(db)
        return {"categoria": categoria, "chave": chave, "valor": valor_str}
    cfg = SystemConfig(
        categoria=categoria,
        chave=chave,
        valor=valor_str,
        tipo=tipo,
        descricao=descricao,
        updated_at=datetime.utcnow(),
    )
    db.add(cfg)
    _commit(db)
    return {"categoria": categoria, "chave": chave, "valor": valor_str}


@router.get("/roles")
def admin_roles() -> list[dict]:
    """Lista os roles disponíveis no sistema."""
    return [{"value": r.value, "label": r.value} for r in UserRole]
