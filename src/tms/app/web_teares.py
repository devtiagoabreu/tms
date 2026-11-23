"""Tela web TMS 8.0: cadastro de teares, edicao e envio de comandos."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from tms import __version__
from tms.app.deps.auth import SESSION_COOKIE_NAME
from tms.core.auth import verify_session_token
from tms.db.base import SessionLocal

router = APIRouter(tags=["teares-web"])

_templates_dir = Path(__file__).parent.parent / "templates"
templates = Jinja2Templates(directory=str(_templates_dir))


def _resolve_user(request: Request):
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        return None
    uid = verify_session_token(token)
    if not uid:
        return None
    db = SessionLocal()
    try:
        from tms.models.auth import User

        user = db.get(User, uid)
        if not user or not user.is_active:
            return None
        return user
    finally:
        db.close()


@router.get("/teares", response_class=HTMLResponse, include_in_schema=False)
def teares_page(request: Request) -> HTMLResponse:
    user = _resolve_user(request)
    if user is None:
        return RedirectResponse(url="/login", status_code=303)
    return templates.TemplateResponse(
        request,
        "teares.html",
        {
            "title": "TMS - Teares",
            "version": __version__,
        },
    )
