"""Páginas web (HTML) do TMS, usando Jinja2 e reutilizando APIs existentes."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from tms import __version__
from tms.app.deps.auth import SESSION_COOKIE_NAME, get_current_user, require_user
from tms.core.auth import create_session_token, verify_password
from tms.db.base import get_db
from tms.models.auth import User

public_router = APIRouter(tags=["web-public"])
router = APIRouter(tags=["web"], dependencies=[Depends(require_user)])

from pathlib import Path
templates_dir = Path(__file__).parent.parent / "templates"
templates = Jinja2Templates(directory=str(templates_dir))

NAV: tuple[dict, ...] = (
    {
        "label": "Visão geral",
        "items": (
            {
                "href": "/",
                "label": "Início",
                "match": ("/",),
                "desc": "Painel inicial com acesso a todas as áreas do TMS.",
                "legacy": "Menu Principal",
                "legacy_path": "tms/index.cgi",
            },
            {
                "href": "/reports",
                "label": "Relatórios",
                "match": ("/reports",),
                "desc": "Consulta consolidada por dia, semana ou mês, filtrando por máquina, intervalo de datas e unidade de medida.",
                "legacy": "Relatorio de Turno / Relatorio por Operador",
                "legacy_path": "tms/shift/select_s.cgi · tms/operator/select_p.cgi",
            },
            {
                "href": "/telas",
                "label": "Telas",
                "match": ("/telas",),
                "desc": "Formulário único que consulta qualquer tela do sistema sem trocar de página.",
                "legacy": "Menu Principal",
                "legacy_path": "tms/index.cgi",
            },
            {
                "href": "/monitor",
                "label": "Monitor",
                "match": ("/monitor",),
                "desc": "Situação das máquinas em tempo real: estado, eficiência, paradas e leitura direta da rede.",
                "legacy": "Display Operacao",
                "legacy_path": "tms/loom/opestate.cgi",
            },
        ),
    },
    {
        "label": "Telas de produção",
        "items": (
            {
                "href": "/screens/efficiency",
                "label": "Eficiência",
                "match": ("/screens/efficiency",),
                "desc": "Eficiência por loom ou operador, com tempo de roda, parada e fios de urdume e trama.",
                "legacy": "Grafico de Eficiencia",
                "legacy_path": "tms/shift/select_s.cgi?mode=efficiency",
            },
            {
                "href": "/screens/production",
                "label": "Produção",
                "match": ("/screens/production",),
                "desc": "Quantidade produzida por loom ou operador no período selecionado.",
                "legacy": "Grafico de Producao",
                "legacy_path": "tms/shift/select_s.cgi?mode=production",
            },
            {
                "href": "/screens/stop-analysis",
                "label": "Análise de Paradas",
                "match": ("/screens/stop-analysis",),
                "desc": "Ranking de paradas por causa, medido em contagem de eventos ou em tempo.",
                "legacy": "Grafico de Analise de Paradas",
                "legacy_path": "tms/shift/select_s.cgi?mode=stopanalysis",
            },
            {
                "href": "/screens/shiftreport",
                "label": "Relatório de Turno",
                "match": ("/screens/shiftreport",),
                "desc": "Indicadores consolidados de cada turno, agrupados por loom ou estilo.",
                "legacy": "Relatorio de Turno",
                "legacy_path": "tms/shift/select_s.cgi?mode=shiftreport",
            },
            {
                "href": "/screens/stylereport",
                "label": "Relatório de Artigo",
                "match": ("/screens/stylereport",),
                "desc": "Desempenho por artigo (estilo) de tecido, com unidade e tipo de feixe.",
                "legacy": "Relatorio de Artigo",
                "legacy_path": "tms/shift/select_s.cgi?mode=stylereport",
            },
            {
                "href": "/screens/showstyle",
                "label": "Histórico de Artigos",
                "match": ("/screens/showstyle",),
                "desc": "Sequência de artigos processados por loom ou estilo, por turno ou operador.",
                "legacy": "Mostrar Historico de Artigos",
                "legacy_path": "tms/edit/showstyle.cgi",
            },
        ),
    },
    {
        "label": "Históricos",
        "items": (
            {
                "href": "/screens/statushistory",
                "label": "Histórico",
                "match": ("/screens/statushistory",),
                "desc": "Evolução do status do equipamento ao longo do período, por loom ou estilo.",
                "legacy": "Historico",
                "legacy_path": "tms/shift/select_s.cgi?mode=statushistory",
            },
            {
                "href": "/screens/stophistory",
                "label": "Histórico de Paradas",
                "match": ("/screens/stophistory",),
                "desc": "Registro detalhado de cada parada com causa e duração dentro do intervalo informado.",
                "legacy": "Historico de Parada",
                "legacy_path": "tms/shift/stophistory.cgi",
            },
            {
                "href": "/screens/svsreport",
                "label": "Relatório de Serviço",
                "match": ("/screens/svsreport",),
                "desc": "Relatório de serviço do turno, com seleção por loom ou estilo e tipo de feixe.",
                "legacy": "Dados Relatorio Servico",
                "legacy_path": "tms/shift2/select_s2.cgi?mode=svsreport",
            },
        ),
    },
    {
        "label": "Sistema",
        "items": (
            {
                "href": "/machines",
                "label": "Máquinas",
                "match": ("/machines",),
                "desc": "Cadastro dos equipamentos com IP e situação, e leitura do snapshot de cada loom.",
                "legacy": "Coleta de Dados(Rede)",
                "legacy_path": "tms/loom/getdata.cgi",
            },
            {
                "href": "/config",
                "label": "Configurações",
                "match": ("/config",),
                "desc": "Edita faixas de IP, lista de artigos, definição de turno e preferências de relatório.",
                "legacy": "Ajuste de Relatorio / Ajuste Artigo / Trocar Ajuste Cronograma",
                "legacy_path": "tms/setting/selitem.cgi · tms/scanset/styleset.cgi",
            },
            {
                "href": "/docs",
                "label": "API /docs",
                "match": ("/docs",),
                "desc": "Documentação interativa dos endpoints JSON e CSV que substituem os CGIs do sistema legado.",
                "legacy": "—",
                "legacy_path": "substitui os CGIs de tms.zip",
            },
        ),
    },
)

templates.env.globals["nav"] = NAV


@router.get("/", response_class=HTMLResponse)
def index_page(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "title": "TMS - Painel",
            "version": __version__,
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


@router.get("/monitor", response_class=HTMLResponse)
def monitor_page_html(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "monitor_fixed.html",
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
