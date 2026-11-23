"""Dashboard web (Fase 2) que consome `/api/monitor`, renderizado via template PDM."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from tms import __version__

router = APIRouter(tags=["dashboard"])

templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))


@router.get("/monitor", response_class=HTMLResponse, include_in_schema=False)
def monitor_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "monitor_dashboard.html",
        {
            "title": "TMS - Monitor",
            "version": __version__,
        },
    )
