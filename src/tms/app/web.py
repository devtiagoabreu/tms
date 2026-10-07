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
