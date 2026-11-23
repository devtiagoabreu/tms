"""Páginas web (HTML) do TMS, usando Jinja2 e reutilizando APIs existentes."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from tms import __version__
from tms.app.deps.auth import SESSION_COOKIE_NAME, get_current_user, require_user
from tms.core.auth import create_session_token, verify_password
from tms.db.base import get_db
from tms.models.auth import User
from tms.models.daily import DailyCollectionItem, DailyCollectionRun, DailyLoomData
from tms.models.navigation import Menu
from tms.services.daily_collection import collection_gaps, get_yesterday
from tms.services.monthly import current_and_previous_months, month_summary

public_router = APIRouter(tags=["web-public"])
router = APIRouter(tags=["web"], dependencies=[Depends(require_user)])

from pathlib import Path
templates_dir = Path(__file__).parent.parent / "templates"
templates = Jinja2Templates(directory=str(templates_dir))


def get_user_menus(db: Session, usuario_id: int) -> list[dict]:
    """Retorna os menus visíveis para o usuário (mesclados por role +
    menus pessoais), ordenados."""
    user = db.get(User, usuario_id)
    if user is None:
        return []

    menus = (
        db.execute(
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
        .scalars()
        .all()
    )

    out = []
    for m in menus:
        items = sorted(m.items, key=lambda i: (i.ordem, i.title))
        out.append(
            {
                "id": m.id,
                "label": m.title,
                "icon": m.icon,
                "url": m.url,
                "ordem": m.ordem,
                "items": [
                    {
                        "href": i.url or "#",
                        "label": i.title,
                        "icon": i.icon,
                        "match": (i.url or "#",),
                        "desc": "",
                    }
                    for i in items if i.active
                ],
            }
        )
    return out


@router.get("/", response_class=HTMLResponse)
def index_page(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    target = get_yesterday()
    run = db.execute(
        select(DailyCollectionRun).where(DailyCollectionRun.collection_date == target)
    ).scalar_one_or_none()

    items, looms = [], []
    if run is not None:
        items = list(
            db.execute(
                select(DailyCollectionItem)
                .where(DailyCollectionItem.run_id == run.id)
                .order_by(DailyCollectionItem.mac_name)
            ).scalars()
        )
        looms = list(
            db.execute(
                select(DailyLoomData)
                .where(DailyLoomData.collection_date == target)
                .order_by(DailyLoomData.mac_name)
            ).scalars()
        )

    missing = [i for i in items if i.status != "success"]
    efficiencies = [r.efficiency for r in looms if r.efficiency is not None]
    rpms = [r.rpm for r in looms if r.rpm is not None]

    def total(attr: str):
        values = [getattr(r, attr) for r in looms if getattr(r, attr) is not None]
        return round(sum(values), 1) if values else None

    summary = {
        "collected": len(looms),
        "missing": len(missing),
        "avg_efficiency": round(sum(efficiencies) / len(efficiencies), 1) if efficiencies else None,
        "avg_rpm": round(sum(rpms) / len(rpms), 1) if rpms else None,
        "total_stops": total("total_stop_ct") or 0,
        "breakdown_known": any(
            r.trama_stops is not None or r.urdume_stops is not None or r.outros_stops is not None
            for r in looms
        ),
        "trama_stops": total("trama_stops"),
        "urdume_stops": total("urdume_stops"),
        "outros_stops": total("outros_stops"),
        "trama_min": total("trama_stops_min"),
        "urdume_min": total("urdume_stops_min"),
        "outros_min": total("outros_stops_min"),
    }

    gaps = collection_gaps(db, days=7)
    gap_days = [row for row in gaps["days"] if row["status"] not in ("completed",)]
    gap_looms = [row for row in gaps["looms"] if row["missing_count"] >= 2]

    (current_start, current_end), (previous_start, previous_end) = (
        current_and_previous_months()
    )
    monthly = {
        "current": month_summary(db, current_start, current_end),
        "previous": month_summary(db, previous_start, previous_end),
    }

    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "title": "TMS - Dashboard",
            "version": __version__,
            "target_date": target,
            "run": run,
            "items": items,
            "looms": looms,
            "missing": missing,
            "summary": summary,
            "monthly": monthly,
            "gaps": gaps,
            "gap_days": gap_days,
            "gap_looms": gap_looms,
            "current_user": getattr(request.state, "user", None),
        },
    )


@router.get("/reports", response_class=HTMLResponse)
def reports_page(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "reports.html",
        {
            "title": "TMS - Relatórios",
            "version": __version__,
        },
    )


@router.get("/reports/daily", response_class=HTMLResponse)
def reports_daily_page(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "reports_daily.html",
        {
            "title": "TMS - Relatório de Coleta Diária",
            "version": __version__,
            "current_view": "day",
            "day_from": None,
            "day_to": None,
        },
    )


@router.get("/reports/loom", response_class=HTMLResponse)
def reports_loom_page(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "reports_daily.html",
        {
            "title": "TMS - Coleta por Tear",
            "version": __version__,
            "current_view": "loom",
            "day_from": None,
            "day_to": None,
        },
    )


@router.get("/reports/style", response_class=HTMLResponse)
def reports_style_page(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "reports_daily.html",
        {
            "title": "TMS - Coleta por Artigo",
            "version": __version__,
            "current_view": "style",
            "day_from": None,
            "day_to": None,
        },
    )


@router.get("/telas", response_class=HTMLResponse)
def telas_page(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "telas.html",
        {
            "title": "TMS - Telas",
            "version": __version__,
        },
    )


@router.get("/config", response_class=HTMLResponse)
def config_page(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "config.html",
        {
            "title": "TMS - Configurações",
            "version": __version__,
        },
    )


@router.get("/config/teares", response_class=HTMLResponse)
def config_teares_page(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    """Página para configurar quais teares são duplos."""
    from tms.models.masters import Machine
    machines = db.execute(select(Machine).order_by(Machine.mac_name)).scalars().all()
    return templates.TemplateResponse(
        request,
        "config_teares.html",
        {
            "title": "TMS - Configurar Teares Duplos",
            "version": __version__,
            "machines": machines,
        },
    )


@router.get("/monitor", response_class=HTMLResponse)
def monitor_page_html(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "monitor.html",
        {
            "title": "TMS - Monitor",
            "version": __version__,
        },
    )


@router.get("/screens/efficiency", response_class=HTMLResponse)
def screen_efficiency(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "screens/efficiency.html", {"title": "TMS - Eficiência", "version": __version__})


@router.get("/screens/production", response_class=HTMLResponse)
def screen_production(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "screens/production.html", {"title": "TMS - Produção", "version": __version__})


@router.get("/screens/stop-analysis", response_class=HTMLResponse)
def screen_stopanalysis(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "screens/stopanalysis.html", {"title": "TMS - Análise de Paradas", "version": __version__})


@router.get("/screens/shiftreport", response_class=HTMLResponse)
def screen_shiftreport(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "screens/shiftreport.html", {"title": "TMS - Relatório de Turno", "version": __version__})


@router.get("/screens/stylereport", response_class=HTMLResponse)
def screen_stylereport(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "screens/stylereport.html", {"title": "TMS - Relatório de Artigo", "version": __version__})


@router.get("/screens/statushistory", response_class=HTMLResponse)
def screen_statushistory(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "screens/statushistory.html", {"title": "TMS - Histórico de Status", "version": __version__})


@router.get("/screens/svsreport", response_class=HTMLResponse)
def screen_svsreport(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "screens/svsreport.html", {"title": "TMS - Relatório de Serviço", "version": __version__})


@router.get("/screens/stophistory", response_class=HTMLResponse)
def screen_stophistory(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "screens/stophistory.html", {"title": "TMS - Histórico de Paradas", "version": __version__})


@router.get("/screens/showstyle", response_class=HTMLResponse)
def screen_showstyle(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "screens/showstyle.html", {"title": "TMS - Histórico de Artigos", "version": __version__})


@router.get("/machines", response_class=HTMLResponse)
def machines_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "machines.html", {"title": "TMS - Máquinas", "version": __version__})


@public_router.get("/login", response_class=HTMLResponse)
def login_page_get(request: Request, user: User | None = Depends(get_current_user)) -> HTMLResponse:
    if user:
        return RedirectResponse(url="/", status_code=303)
    return templates.TemplateResponse(request, "auth/login.html", {"title": "Entrar • TMS", "version": __version__})


@public_router.post("/login")
async def login_page_post(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    email = (form.get("email") or "").strip()
    password = (form.get("password") or "").strip()
    if not email or not password:
        return templates.TemplateResponse(
            request,
            "auth/login.html",
            {"title": "Entrar • TMS", "version": __version__, "error": "Preencha e-mail/usuário e senha."},
            status_code=400,
        )
    stmt = select(User).where((User.email == email) | (User.username == email))
    user = db.execute(stmt).scalar_one_or_none()
    if not user or not user.is_active or not verify_password(password, user.password_hash):
        return templates.TemplateResponse(
            request,
            "auth/login.html",
            {"title": "Entrar • TMS", "version": __version__, "error": "Usuário ou senha inválidos."},
            status_code=401,
        )
    user.last_login_at = datetime.utcnow()
    db.commit()
    token = create_session_token(user.id)
    resp = RedirectResponse(url="/", status_code=303)
    resp.set_cookie(SESSION_COOKIE_NAME, token, httponly=True, samesite="lax", max_age=60 * 60 * 8, path="/")
    return resp


@public_router.get("/logout")
def logout_page():
    resp = RedirectResponse(url="/login", status_code=303)
    resp.delete_cookie(SESSION_COOKIE_NAME, path="/")
    return resp
