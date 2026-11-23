"""Aplicação FastAPI."""

from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta

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
from tms.app.api.admin import router as admin_router
from tms.app.api.cadastros import router as cadastros_router
from tms.app.api.collector import router as collector_router
from tms.app.api.menus import router as menus_router
from tms.app.api.roles import router as roles_router
from tms.app.api.shift_turns import router as shift_turns_router
from tms.app.api.teares import router as teares_router
from tms.app.api.screens import router as screens_router
from tms.app.api.settings import router as settings_router
from tms.app.api.stops import router as stops_router
from tms.app.dashboard import router as dashboard_router
from tms.app.shift_turns import router as shift_turns_web_router
from tms.app.web_cadastros import router as cadastros_web_router
from tms.app.web_menus import router as menus_web_router
from tms.app.web_roles import router as roles_web_router
from tms.app.web_teares import router as teares_web_router
from tms.app.deps.auth import SESSION_COOKIE_NAME
from tms.app.web import public_router, router as web_router
from tms.collector import send_command_to_loom
from tms.core.auth import verify_session_token
from tms.db.base import SessionLocal
from tms.models.auth import User
from tms.models.collector_state import CollectorState
from tms.models.loom_command import LoomCommand
from tms.models.masters import Machine
from tms.services.daily_collection import ensure_daily_collection
from tms.services.live_collection import collect_live_once

log = logging.getLogger(__name__)


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


DAILY_CHECK_INTERVAL_S = 30 * 60

# Intervalo da coleta ao vivo que alimenta ``live_status`` (0 desliga).
LIVE_COLLECT_INTERVAL_S = _env_int("TMS_COLLECT_INTERVAL", 60)
LIVE_COLLECT_TIMEOUT_S = _env_int("TMS_COLLECT_TIMEOUT", 10)


async def _daily_collection_loop() -> None:
    """Garante a coleta diária e reprocessa a fila de retentativa."""
    while True:
        try:
            await asyncio.to_thread(_run_daily_check)
        except Exception:  # pragma: no cover - nunca derruba o servidor
            log.exception("Falha na verificação da coleta diária")
        await asyncio.sleep(DAILY_CHECK_INTERVAL_S)


async def _live_collection_loop() -> None:
    """Persiste o status de todos os teares continuamente (histórico do dia)."""
    while True:
        try:
            await asyncio.to_thread(_run_live_check)
        except Exception:  # pragma: no cover - nunca derruba o servidor
            log.exception("Falha na coleta ao vivo")
        await asyncio.sleep(LIVE_COLLECT_INTERVAL_S)


def _run_daily_check() -> None:
    db = SessionLocal()
    try:
        ensure_daily_collection(db)
    finally:
        db.close()


def _run_live_check() -> None:
    db = SessionLocal()
    try:
        collect_live_once(db, timeout=float(LIVE_COLLECT_TIMEOUT_S))
        _save_collector_state(db)
    finally:
        db.close()


def _save_collector_state(db) -> None:
    """Persiste o estado do coletor contínuo (última/próxima coleta)."""
    state = db.get(CollectorState, 1)
    if state is None:
        state = CollectorState(id=1)
        db.add(state)
    now = datetime.utcnow()
    state.last_collected_at = now
    state.next_collect_at = (
        now + timedelta(seconds=LIVE_COLLECT_INTERVAL_S)
        if LIVE_COLLECT_INTERVAL_S > 0
        else None
    )
    state.interval_s = LIVE_COLLECT_INTERVAL_S
    state.enabled = LIVE_COLLECT_INTERVAL_S > 0
    db.commit()


COMMAND_SEND_INTERVAL_S = 10  # varre a fila de comandos a cada 10s


async def _command_sender_loop() -> None:
    """Envia automaticamente comandos pendentes para os teares."""
    while True:
        try:
            await asyncio.to_thread(_run_command_sender)
        except Exception:  # pragma: no cover - nunca derruba o servidor
            log.exception("Falha no envio de comandos para teares")
        await asyncio.sleep(COMMAND_SEND_INTERVAL_S)


def _run_command_sender() -> None:
    db = SessionLocal()
    try:
        cmds = db.execute(
            select(LoomCommand).where(LoomCommand.status == "pending").limit(50)
        ).scalars().all()
        for cmd in cmds:
            m = db.get(Machine, cmd.machine_id)
            if m is None or not m.ip_addr:
                cmd.status = "error"
                cmd.error_message = "Tear sem IP configurado"
                continue
            sucesso, erro = send_command_to_loom(
                m.ip_addr, cmd.command_type, cmd.payload, timeout=10.0
            )
            cmd.status = "sent" if sucesso else "error"
            cmd.sent_at = datetime.utcnow() if sucesso else None
            cmd.error_message = erro
            db.commit()
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    tasks = [
        asyncio.create_task(_daily_collection_loop()),
        asyncio.create_task(_command_sender_loop()),
    ]
    if LIVE_COLLECT_INTERVAL_S > 0:
        tasks.append(asyncio.create_task(_live_collection_loop()))
    try:
        yield
    finally:
        for task in tasks:
            task.cancel()
        for task in tasks:
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
    """Resolve usuário da sessão e injeta menus no request.state."""
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

    # Injeta menus do usuário no request.state para uso nos templates
    db = SessionLocal()
    try:
        from tms.app.web import get_user_menus

        request.state.user_menus = get_user_menus(db, user.id)
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
app.include_router(daily_router)
app.include_router(collector_router)
app.include_router(shift_turns_router)
app.include_router(cadastros_router)
app.include_router(menus_router)
app.include_router(roles_router)
app.include_router(teares_router)
app.include_router(shift_turns_web_router)
app.include_router(cadastros_web_router)
app.include_router(menus_web_router)
app.include_router(roles_web_router)
app.include_router(teares_web_router)
app.include_router(dashboard_router)
app.include_router(admin_router)
app.include_router(public_router)
app.include_router(web_router)

try:
    app.mount("/static", StaticFiles(directory="src/tms/static"), name="static")
except Exception:
    try:
        app.mount("/static", StaticFiles(directory="tms/static"), name="static")
    except Exception:
        pass
