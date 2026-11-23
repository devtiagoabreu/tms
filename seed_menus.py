"""Seed de menus iniciais para o TMS 8.0.

Executa uma única vez para popular as tabelas de menus com os itens padrão,
baseado no NAV anterior do web.py. Usuários podem depois editar, reordenar,
criar seus próprios menus pessoais e vincular a grupos/turnos.
"""

from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from tms.db.base import SessionLocal, engine
from tms.models.navigation import Menu, MenuItem
from tms.models.auth import User, UserRole
from sqlalchemy import select


MENUS_SEED = [
    {
        "title": "Visão geral",
        "icon": "dashboard",
        "ordem": 1,
        "role": None,  # global
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
            {"title": "Cadastro de Turnos", "url": "/turnos", "icon": "clock", "ordem": 7},
            {"title": "API /docs", "url": "/docs", "icon": "code", "ordem": 8},
        ],
    },
]


def seed_menus() -> None:
    db = SessionLocal()
    try:
        # Só seed se não houver menus cadastrados
        existente = db.execute(select(Menu)).scalar_one_or_none()
        if existente:
            print("Já existem menus cadastrados. Pulando seed.")
            return

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
        db.commit()
        print(f"Seed concluído: {len(MENUS_SEED)} menus criados.")
    finally:
        db.close()


if __name__ == "__main__":
    seed_menus()
