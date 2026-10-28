"""Aplicação FastAPI."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select

from tms import __version__
from tms.app.api.health import router as health_router
from tms.app.api.monitor import router as monitor_router
from tms.app.api.reports import router as reports_router
from tms.app.api.runtime import router as runtime_router
from tms.app.api.screens import router as screens_router
from tms.app.api.settings import router as settings_router
from tms.app.api.stops import router as stops_router
from tms.app.dashboard import router as dashboard_router
from tms.app.deps.auth import SESSION_COOKIE_NAME
from tms.app.web import public_router, router as web_router
from tms.core.auth import verify_session_token
from tms.db.base import SessionLocal
from tms.models.auth import User

app = FastAPI(title="TMS — Toyota Loom Monitoring System", version=__version__)


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    path = request.url.path
    public_paths = (
        "/login",
        "/logout",
        "/static",
        "/docs",
        "/openapi.json",
        "/redoc",
    )
    if any(path == p or path.startswith(p + "/") for p in public_paths):
        return await call_next(request)
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        return RedirectResponse(url="/login", status_code=303)
    uid = verify_session_token(token)
    if not uid:
        resp = RedirectResponse(url="/login", status_code=303)
        resp.delete_cookie(SESSION_COOKIE_NAME, path="/")
        return resp
    db = SessionLocal()
    try:
        user = db.get(User, uid)
        if not user or not user.is_active:
            resp = RedirectResponse(url="/login", status_code=303)
            resp.delete_cookie(SESSION_COOKIE_NAME, path="/")
            return resp
        request.state.user = user
    finally:
        db.close()
    return await call_next(request)


app.include_router(health_router)
app.include_router(runtime_router)
app.include_router(reports_router)
app.include_router(monitor_router)
app.include_router(screens_router)
app.include_router(settings_router)
app.include_router(stops_router)
app.include_router(dashboard_router)
app.include_router(public_router)
app.include_router(web_router)

try:
    app.mount("/static", StaticFiles(directory="src/tms/static"), name="static")
except Exception:
    try:
        app.mount("/static", StaticFiles(directory="tms/static"), name="static")
    except Exception:
        pass


@app.get("/")
def root() -> dict:
    return {"name": "TMS", "version": __version__}