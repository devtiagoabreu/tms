"""Seed completo de dados iniciais para o TMS 8.0.

Executa uma única vez para popular:
- Menus e submenus (tela /menus)
- Grupos de teares e membros (tela /cadastros)
- Operadores vinculados a grupos
- Turnos de produção (tela /turnos)
- Teares (tela /teares)
- Roles e permissões (tela /roles)

Uso:
    set PYTHONPATH=src
    python seed_completo.py
"""

from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from tms.db.base import SessionLocal
from tms.models.navigation import Menu, MenuItem
from tms.models.machine_group import MachineGroup, MachineGroupMember
from tms.models.masters import Machine, Operator
from tms.models.shift_turn import ShiftTurn
from tms.models.permission import Permission, RolePermission
from tms.models.auth import User, UserRole
from sqlalchemy import select


# ============================================================================
# 1. MENUS E ITENS (tela /menus)
# ============================================================================
MENUS_SEED = [
    {
        "title": "Visão geral",
        "icon": "dashboard",
        "ordem": 1,
        "role": None,
        "items": [
            {"title": "Dashboard", "url": "/", "icon": "dashboard", "ordem": 1},
            {"title": "Relatórios", "url": "/reports", "icon": "reports", "ordem": 2},
            {"title": "Coleta por Dia", "url": "/reports/daily", "icon": "calendar", "ordem": 3},
            {"title": "Coleta por Tear", "url": "/reports/loom", "icon": "cpu", "ordem": 4},
            {"title": "Coleta por Artigo", "url": "/reports/style", "icon": "tag", "ordem": 5},
            {"title": "Telas", "url": "/telas", "icon": "layers", "ordem": 6},
            {"title": "Monitor", "url": "/monitor", "icon": "monitor", "ordem": 7},
        ],
    },
    {
        "title": "Telas de produção",
        "icon": "chart",
        "ordem": 2,
        "role": None,
        "items": [
            {"title": "Eficiência", "url": "/screens/efficiency", "icon": "bolt", "ordem": 1},
            {"title": "Produção", "url": "/screens/production", "icon": "box", "ordem": 2},
            {"title": "Análise de Paradas", "url": "/screens/stop-analysis", "icon": "alert", "ordem": 3},
            {"title": "Relatório de Turno", "url": "/screens/shiftreport", "icon": "clock", "ordem": 4},
            {"title": "Relatório de Artigo", "url": "/screens/stylereport", "icon": "tag", "ordem": 5},
            {"title": "Histórico de Artigos", "url": "/screens/showstyle", "icon": "list", "ordem": 6},
        ],
    },
    {
        "title": "Históricos",
        "icon": "history",
        "ordem": 3,
        "role": None,
        "items": [
            {"title": "Histórico", "url": "/screens/statushistory", "icon": "activity", "ordem": 1},
            {"title": "Histórico de Paradas", "url": "/screens/stophistory", "icon": "history", "ordem": 2},
            {"title": "Relatório de Serviço", "url": "/screens/svsreport", "icon": "wrench", "ordem": 3},
        ],
    },
    {
        "title": "Sistema",
        "icon": "settings",
        "ordem": 4,
        "role": None,
        "items": [
            {"title": "Máquinas", "url": "/machines", "icon": "cpu", "ordem": 1},
            {"title": "Configurações", "url": "/config", "icon": "settings", "ordem": 2},
            {"title": "Teares Duplos", "url": "/config/teares", "icon": "cpu", "ordem": 3},
            {"title": "Grupos de Teares", "url": "/cadastros", "icon": "cpu", "ordem": 4},
            {"title": "Cadastro de Teares", "url": "/teares", "icon": "cpu", "ordem": 5},
            {"title": "Configurar Menus", "url": "/menus", "icon": "settings", "ordem": 6},
            {"title": "Roles e Permissões", "url": "/roles", "icon": "settings", "ordem": 7},
            {"title": "API /docs", "url": "/docs", "icon": "code", "ordem": 8},
        ],
    },
]

# ============================================================================
# 2. TURNOS DE PRODUÇÃO (tela /turnos)
# ============================================================================
# Máscara de bits: bit0=domingo(1), bit1=segunda(2), bit2=terça(4),
# bit3=quarta(8), bit4=quinta(16), bit5=sexta(32), bit6=sábado(64)
# Seg-Sex = 2+4+8+16+32 = 62
# Seg-Sáb = 2+4+8+16+32+64 = 126

TURNOS_SEED = [
    {"name": "A", "start_time": "05:00", "end_time": "14:00", "active": True,
     "days_mask": 62, "wraps_midnight": False, "sort_order": 1},
    {"name": "B", "start_time": "14:00", "end_time": "23:35", "active": True,
     "days_mask": 62, "wraps_midnight": False, "sort_order": 2},
    {"name": "C", "start_time": "23:35", "end_time": "05:00", "active": False,
     "days_mask": 62, "wraps_midnight": True, "sort_order": 3},
    {"name": "A (Sábado)", "start_time": "06:00", "end_time": "10:00", "active": True,
     "days_mask": 64, "wraps_midnight": False, "sort_order": 4},
]

# ============================================================================
# 3. GRUPOS DE TEARES (tela /cadastros)
# ============================================================================
GRUPOS_SEED = [
    {"name": "Setor A", "description": "Setor A - Turnos A e B", "shift_turn_name": "A", "active": True},
    {"name": "Setor B", "description": "Setor B - Turno B", "shift_turn_name": "B", "active": True},
    {"name": "LWT", "description": "Teares LWT", "shift_turn_name": None, "active": True},
    {"name": "JAT", "description": "Teares JAT", "shift_turn_name": None, "active": True},
]

# Membros dos grupos (mac_name -> grupo)
GRUPOS_MEMBROS_SEED = {
    "Setor A": ["00001", "00002", "00003"],
    "Setor B": ["00004", "00005", "00006"],
    "LWT": ["00007", "00008"],
    "JAT": ["00001", "00002", "00003", "00004", "00005", "00006"],
}

# ============================================================================
# 4. TEARES (tela /teares)
# ============================================================================
TEARES_SEED = [
    {"mac_name": "00001", "mac_type": "JAT", "ip_addr": "10.0.0.11", "grupo": "Setor A", "is_double": False, "active": True},
    {"mac_name": "00002", "mac_type": "JAT", "ip_addr": "10.0.0.12", "grupo": "Setor A", "is_double": False, "active": True},
    {"mac_name": "00003", "mac_type": "JAT", "ip_addr": "10.0.0.13", "grupo": "Setor A", "is_double": False, "active": True},
    {"mac_name": "00004", "mac_type": "JAT", "ip_addr": "10.0.0.14", "grupo": "Setor B", "is_double": False, "active": True},
    {"mac_name": "00005", "mac_type": "JAT", "ip_addr": "10.0.0.15", "grupo": "Setor B", "is_double": False, "active": True},
    {"mac_name": "00006", "mac_type": "JAT", "ip_addr": "10.0.0.16", "grupo": "Setor B", "is_double": True, "active": True},
    {"mac_name": "00007", "mac_type": "LWT", "ip_addr": "10.0.0.21", "grupo": "LWT", "is_double": False, "active": True},
    {"mac_name": "00008", "mac_type": "LWT", "ip_addr": "10.0.0.22", "grupo": "LWT", "is_double": False, "active": True},
]

# ============================================================================
# 5. OPERADORES (tela /cadastros)
# ============================================================================
OPERADORES_SEED = [
    {"code": "001", "name": "João Silva", "role": "tecelao", "grupo": "Setor A", "shift_day": "A", "active": True},
    {"code": "002", "name": "Maria Santos", "role": "tecelao", "grupo": "Setor A", "shift_day": "A", "active": True},
    {"code": "003", "name": "Pedro Oliveira", "role": "contra_mestre", "grupo": "Setor B", "shift_day": "B", "active": True},
    {"code": "004", "name": "Ana Costa", "role": "tecelao", "grupo": "Setor B", "shift_day": "B", "active": True},
    {"code": "005", "name": "Carlos Ferreira", "role": "supervisor", "grupo": None, "shift_day": None, "active": True},
]

# ============================================================================
# 6. ROLES E PERMISSÕES (tela /roles)
# ============================================================================
PERMISSOES_SEED = [
    ("teares.ver", "Ver teares", "teares"),
    ("teares.editar", "Editar teares", "teares"),
    ("teares.comandos", "Enviar comandos para teares", "teares"),
    ("coletar.executar", "Executar coleta manual", "coletar"),
    ("menus.configurar", "Configurar menus e submenus", "menus"),
    ("menus.ver", "Ver menus", "menus"),
    ("cadastros.ver", "Ver cadastros (grupos, operadores)", "cadastros"),
    ("cadastros.editar", "Editar cadastros", "cadastros"),
    ("relatorios.ver", "Ver relatórios", "relatorios"),
    ("monitor.ver", "Ver monitor ao vivo", "monitor"),
    ("admin.usuarios", "Gerenciar usuários e roles", "admin"),
]

ROLE_PERMISSOES_SEED = {
    "admin": [p[0] for p in PERMISSOES_SEED],
    "operador": [
        "teares.ver", "coletar.executar", "menus.ver", "cadastros.ver",
        "relatorios.ver", "monitor.ver",
    ],
    "visualizador": [
        "teares.ver", "menus.ver", "cadastros.ver", "relatorios.ver", "monitor.ver",
    ],
}


def limpar_banco(db) -> None:
    """Remove todos dados do seed para reexecução limpa."""
    from tms.models.navigation import MenuItem, Menu
    from tms.models.machine_group import MachineGroupMember
    from tms.models.permission import RolePermission

    # Ordem importa por causa das foreign keys
    db.execute(select(MenuItem)).scalars().all()  # apenas garantir carregamento
    db.query(MenuItem).delete()
    db.query(Menu).delete()
    db.query(MachineGroupMember).delete()
    db.query(MachineGroup).delete()
    db.query(RolePermission).delete()
    db.query(Permission).delete()
    db.query(Operator).delete()
    db.query(Machine).delete()
    db.query(ShiftTurn).delete()
    db.commit()


def seed() -> None:
    db = SessionLocal()
    try:
        existente = db.execute(select(Menu)).scalar_one_or_none()
        if existente:
            print("Já existem dados no banco. Use limpar_banco() primeiro ou edite manualmente.")
            return

        # ---- Menus ----
        for m_data in MENUS_SEED:
            menu = Menu(
                title=m_data["title"],
                icon=m_data.get("icon"),
                ordem=m_data.get("ordem", 0),
                role=m_data.get("role"),
                active=True,
            )
            db.add(menu)
            db.flush()
            for i_data in m_data.get("items", []):
                item = MenuItem(
                    menu_id=menu.id,
                    title=i_data["title"],
                    url=i_data.get("url"),
                    icon=i_data.get("icon"),
                    ordem=i_data.get("ordem", 0),
                    active=True,
                )
                db.add(item)
        print(f"✅ {len(MENUS_SEED)} menus criados.")

        # ---- Turnos ----
        for t_data in TURNOS_SEED:
            turno = ShiftTurn(
                name=t_data["name"],
                start_time=t_data["start_time"],
                end_time=t_data["end_time"],
                active=t_data["active"],
                days_mask=t_data["days_mask"],
                wraps_midnight=t_data["wraps_midnight"],
                sort_order=t_data["sort_order"],
            )
            db.add(turno)
        db.flush()
        print(f"✅ {len(TURNOS_SEED)} turnos criados.")

        # Mapear nomes de turno para id
        turnos_map = {}
        for t in db.execute(select(ShiftTurn)).scalars().all():
            turnos_map[t.name] = t.id

        # ---- Grupos de teares ----
        grupos_map = {}
        for g_data in GRUPOS_SEED:
            shift_turn_id = turnos_map.get(g_data["shift_turn_name"]) if g_data["shift_turn_name"] else None
            grupo = MachineGroup(
                name=g_data["name"],
                description=g_data.get("description"),
                shift_turn_id=shift_turn_id,
                active=g_data.get("active", True),
            )
            db.add(grupo)
            db.flush()
            grupos_map[g_data["name"]] = grupo.id
        print(f"✅ {len(GRUPOS_SEED)} grupos criados.")

        # ---- Teares ----
        maquinas_map = {}
        for t_data in TEARES_SEED:
            grupo_id = grupos_map.get(t_data["grupo"])
            maquina = Machine(
                mac_name=t_data["mac_name"],
                mac_type=t_data["mac_type"],
                ip_addr=t_data["ip_addr"],
                active=t_data.get("active", True),
                is_double=t_data.get("is_double", False),
            )
            db.add(maquina)
            db.flush()
            maquinas_map[t_data["mac_name"]] = maquina.id

            # Vincular ao grupo
            if grupo_id:
                membro = MachineGroupMember(
                    group_id=grupo_id,
                    machine_id=maquina.id,
                )
                db.add(membro)
        print(f"✅ {len(TEARES_SEED)} teares criados e vinculados a grupos.")

        # ---- Operadores ----
        for o_data in OPERADORES_SEED:
            grupo_id = grupos_map.get(o_data["grupo"]) if o_data["grupo"] else None
            operador = Operator(
                code=o_data["code"],
                name=o_data["name"],
                role=o_data.get("role", "tecelao"),
                shift_day=o_data.get("shift_day"),
                group_id=grupo_id,
                active=o_data.get("active", True),
            )
            db.add(operador)
        print(f"✅ {len(OPERADORES_SEED)} operadores criados.")

        # ---- Permissões e Roles ----
        permissoes_map = {}
        for chave, descricao, modulo in PERMISSOES_SEED:
            perm = Permission(
                chave=chave,
                descricao=descricao,
                modulo=modulo,
                active=True,
            )
            db.add(perm)
            db.flush()
            permissoes_map[chave] = perm.id

        for role, chaves in ROLE_PERMISSOES_SEED.items():
            for chave in chaves:
                rp = RolePermission(
                    role=role,
                    permission_id=permissoes_map[chave],
                    active=True,
                )
                db.add(rp)
        print(f"✅ {len(PERMISSOES_SEED)} permissões e roles configuradas.")

        db.commit()
        print("\n🎉 Seed completo concluído com sucesso!")
        print("\nResumo:")
        print(f"  - {len(MENUS_SEED)} menus com submenus")
        print(f"  - {len(TURNOS_SEED)} turnos (A, B, C, A Sábado)")
        print(f"  - {len(GRUPOS_SEED)} grupos de teares")
        print(f"  - {len(TEARES_SEED)} teares")
        print(f"  - {len(OPERADORES_SEED)} operadores")
        print(f"  - {len(PERMISSOES_SEED)} permissões em 3 roles")

    except Exception as e:
        db.rollback()
        print(f"❌ Erro no seed: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    import sys

    if "--limpar" in sys.argv:
        limpar = SessionLocal()
        try:
            limpar_banco(limpar)
            print("Banco limpo com sucesso.")
        finally:
            limpar.close()

    seed()
