"""Aplicação FastAPI."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select

from tms import __version__
from tms.app.api.daily import router as daily_router
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
from tms.services.daily_collection import ensure_daily_collection

log = logging.getLogger(__name__)

DAILY_CHECK_INTERVAL_S = 30 * 60


async def _daily_collection_loop() -> None:
    """Garante a coleta diária e reprocessa a fila de retentativa."""
    while True:
        try:
            await asyncio.to_thread(_run_daily_check)
        except Exception:  # pragma: no cover - nunca derruba o servidor
            log.exception("Falha na verificação da coleta diária")
        await asyncio.sleep(DAILY_CHECK_INTERVAL_S)


def _run_daily_check() -> None:
    db = SessionLocal()
    try:
        ensure_daily_collection(db)
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(_daily_collection_loop())
    try:
        yield
    finally:
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass


app = FastAPI(
    title="TMS — Toyota Loom Monitoring System",
    version=__version__,
    lifespan=lifespan,
)


def _resolve_user(token: str | None) -> User | None:
    """Valida o cookie de sessão e devolve o usuário ativo (ou None)."""
    if not token:
        return None
    uid = verify_session_token(token)
    if not uid:
        return None
    db = SessionLocal()
    try:
        user = db.get(User, uid)
        if not user or not user.is_active:
            return None
        db.expunge(user)
        return user
    finally:
        db.close()


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

    user = _resolve_user(request.cookies.get(SESSION_COOKIE_NAME))
    if user is None:
        if path.startswith("/api/"):
            return JSONResponse({"detail": "Não autenticado"}, status_code=401)
        resp = RedirectResponse(url="/login", status_code=303)
        resp.delete_cookie(SESSION_COOKIE_NAME, path="/")
        return resp

    request.state.user = user
    return await call_next(request)


app.include_router(health_router)
app.include_router(runtime_router)
app.include_router(reports_router)
app.include_router(monitor_router)
app.include_router(screens_router)
app.include_router(settings_router)
app.include_router(stops_router)
app.include_router(daily_router)
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
