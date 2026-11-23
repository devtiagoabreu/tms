"""Telas web de cadastros TMS 8.0: grupos, membros e operadores."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from tms import __version__
from tms.app.deps.auth import SESSION_COOKIE_NAME
from tms.core.auth import verify_session_token
from tms.db.base import SessionLocal

router = APIRouter(tags=["cadastros-web"])

templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))

DAYS_OF_WEEK = [
    ("domingo", "Domingo", 1),
    ("segunda", "Segunda", 2),
    ("terca", "Terça", 4),
    ("quarta", "Quarta", 8),
    ("quinta", "Quinta", 16),
    ("sexta", "Sexta", 32),
    ("snado", "Sábado", 64),
]


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


def _require_auth(request: Request):
    user = _resolve_user(request)
    if user is None:
        return RedirectResponse(url="/login", status_code=303)
    return user


@router.get("/cadastros", response_class=HTMLResponse, include_in_schema=False)
def cadastros_page(request: Request) -> HTMLResponse:
    user = _resolve_user(request)
    if user is None:
        return RedirectResponse(url="/login", status_code=303)
    return templates.TemplateResponse(
        request,
        "cadastros.html",
        {
            "title": "TMS - Cadastros",
            "version": __version__,
        },
    )
