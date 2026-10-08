"""Páginas web (HTML) do TMS, usando Jinja2 e reutilizando APIs existentes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from tms import __version__
from tms.db.base import get_db

router = APIRouter(tags=["web"])

templates = Jinja2Templates(directory="src/tms/templates")


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
        "monitor.html",
        {
            "title": "TMS - Monitor",
            "version": __version__,
        },
    )


@router.get("/screens/efficiency", response_class=HTMLResponse)
def screen_efficiency(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "screens/efficiency.html", {"title": "TMS - Efficiency", "version": __version__})


@router.get("/screens/production", response_class=HTMLResponse)
def screen_production(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "screens/production.html", {"title": "TMS - Production", "version": __version__})


@router.get("/screens/stop-analysis", response_class=HTMLResponse)
def screen_stopanalysis(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "screens/stopanalysis.html", {"title": "TMS - Stop Analysis", "version": __version__})


@router.get("/screens/shiftreport", response_class=HTMLResponse)
def screen_shiftreport(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "screens/shiftreport.html", {"title": "TMS - Shift Report", "version": __version__})


@router.get("/screens/stylereport", response_class=HTMLResponse)
def screen_stylereport(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "screens/stylereport.html", {"title": "TMS - Style Report", "version": __version__})


@router.get("/screens/statushistory", response_class=HTMLResponse)
def screen_statushistory(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "screens/statushistory.html", {"title": "TMS - Status History", "version": __version__})


@router.get("/screens/svsreport", response_class=HTMLResponse)
def screen_svsreport(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "screens/svsreport.html", {"title": "TMS - SVS Report", "version": __version__})


@router.get("/screens/stophistory", response_class=HTMLResponse)
def screen_stophistory(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "screens/stophistory.html", {"title": "TMS - Stop History", "version": __version__})


@router.get("/screens/showstyle", response_class=HTMLResponse)
def screen_showstyle(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "screens/showstyle.html", {"title": "TMS - Show Style", "version": __version__})


@router.get("/machines", response_class=HTMLResponse)
def machines_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "machines.html", {"title": "TMS - Máquinas", "version": __version__})
