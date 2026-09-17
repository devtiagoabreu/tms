"""Aplicação FastAPI."""

from __future__ import annotations

from fastapi import FastAPI

from tms import __version__
from tms.app.api.health import router as health_router

app = FastAPI(title="TMS — Toyota Loom Monitoring System", version=__version__)

app.include_router(health_router)


@app.get("/")
def root() -> dict:
    return {"name": "TMS", "version": __version__}