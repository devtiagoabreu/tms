from __future__ import annotations

import os


class Config:
    """Configuração via ambiente (rasa, sem dependência extra)."""

    database_url: str = os.getenv("TMS_DATABASE_URL", "postgresql+psycopg://tms:tms@localhost:5432/tms")
    debug: bool = os.getenv("TMS_DEBUG", "0") == "1"
    default_language: str = os.getenv("TMS_LANGUAGE", "en")
    collect_expire_hours: int = int(os.getenv("TMS_COLLECT_EXPIRE", "26"))


config = Config()