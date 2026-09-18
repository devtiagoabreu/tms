"""Endpoints de configuração/edição (Fase 4)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from tms import config_service as cfg
from tms.app.api.schemas import PrefsPayload, TextPayload, ValuePayload
from tms.db.base import get_db

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("")
def list_settings(db: Session = Depends(get_db)) -> dict:
    return cfg.all_settings(db)


@router.get("/ip-ranges")
def get_ip_ranges(db: Session = Depends(get_db)) -> dict:
    ranges = cfg.get_ip_ranges(db)
    return {
        "ranges": [list(r) for r in ranges],
        "ips": cfg.expand_ip_ranges(ranges),
        "text": cfg.format_ip_ranges(ranges),
    }


@router.put("/ip-ranges")
def put_ip_ranges(payload: TextPayload, db: Session = Depends(get_db)) -> dict:
    ranges = cfg.replace_ip_ranges(db, payload.text)
    db.commit()
    return {"ranges": [list(r) for r in ranges], "ips": cfg.expand_ip_ranges(ranges)}


@router.get("/styles")
def get_styles(db: Session = Depends(get_db)) -> dict:
    styles = cfg.get_styles(db)
    return {"styles": styles, "text": cfg.format_styles(styles)}


@router.put("/styles")
def put_styles(payload: TextPayload, db: Session = Depends(get_db)) -> dict:
    styles = cfg.replace_styles(db, payload.text)
    db.commit()
    return {"styles": styles}


@router.get("/shift")
def get_shift(db: Session = Depends(get_db)) -> dict:
    return cfg.get_shift_schedule(db)


@router.put("/shift")
def put_shift(payload: TextPayload, db: Session = Depends(get_db)) -> dict:
    schedule = cfg.replace_shift_schedule(db, payload.text)
    db.commit()
    return schedule


@router.get("/report-prefs")
def get_report_prefs(db: Session = Depends(get_db)) -> dict:
    return cfg.get_report_prefs(db)


@router.put("/report-prefs")
def put_report_prefs(payload: PrefsPayload, db: Session = Depends(get_db)) -> dict:
    prefs = cfg.replace_report_prefs(db, payload.prefs)
    db.commit()
    return prefs


@router.get("/value/{key}")
def get_value(key: str, db: Session = Depends(get_db)) -> dict:
    return {"key": key, "value": cfg.get_setting(db, key)}


@router.put("/value/{key}")
def put_value(key: str, payload: ValuePayload, db: Session = Depends(get_db)) -> dict:
    cfg.set_setting(db, key, payload.value)
    db.commit()
    return {"key": key, "value": payload.value}
