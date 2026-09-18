"""Aplicação FastAPI."""

from __future__ import annotations

from fastapi import FastAPI

from tms import __version__
from tms.app.api.health import router as health_router
from tms.app.api.monitor import router as monitor_router
from tms.app.api.reports import router as reports_router
from tms.app.api.runtime import router as runtime_router
from tms.app.api.settings import router as settings_router
from tms.app.dashboard import router as dashboard_router

app = FastAPI(title="TMS — Toyota Loom Monitoring System", version=__version__)

app.include_router(health_router)
app.include_router(runtime_router)
app.include_router(reports_router)
app.include_router(monitor_router)
app.include_router(settings_router)
app.include_router(dashboard_router)


@app.get("/")
def root() -> dict:
    return {"name": "TMS", "version": __version__}