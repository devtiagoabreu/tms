"""Schemas de resposta da API de leitura."""

from __future__ import annotations

from datetime import datetime
from typing import Any, List, Optional

from pydantic import BaseModel, ConfigDict


class _Base(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class MachineOut(_Base):
    id: int
    mac_name: str
    mac_type: str
    ip_addr: Optional[str] = None
    active: bool


class SnapshotOut(_Base):
    id: int
    machine_id: int
    mac_name: Optional[str] = None
    shift_id: Optional[str] = None
    get_time: Optional[datetime] = None
    sys_time: Optional[datetime] = None
    rtc_time: Optional[datetime] = None
    style: Optional[str] = None
    beam: Optional[str] = None
    ubeam: Optional[str] = None
    s_beam: Optional[str] = None
    r_beam: Optional[str] = None
    cloth_len: Optional[str] = None
    cut_len: Optional[str] = None
    doff_fcst: Optional[int] = None
    wout_fcst: Optional[int] = None
    uwout_fcst: Optional[int] = None


class DailyRawOut(_Base):
    id: int
    machine_id: int
    mac_name: Optional[str] = None
    day: str
    shift_id: Optional[str] = None
    seisan: Optional[dict] = None
    run_tm: Optional[int] = None
    stop_ttm: Optional[int] = None
    s_ct: Optional[List[int]] = None
    s_tm: Optional[List[int]] = None
    raw_line: Optional[str] = None


class AggShiftOut(_Base):
    id: int
    shift_id: str
    machine_id: Optional[int] = None
    mac_name: Optional[str] = None
    operator_id: Optional[int] = None
    style: Optional[str] = None
    beam: Optional[str] = None
    ubeam: Optional[str] = None
    seisan_1: Optional[float] = None
    seisan_2: Optional[float] = None
    seisan_3: Optional[float] = None
    off_prod_1: Optional[float] = None
    off_prod_2: Optional[float] = None
    off_prod_3: Optional[float] = None
    run_tm: Optional[float] = None
    stop_ttm: Optional[float] = None
    effic: Optional[float] = None
    stop_ct: Optional[List[int]] = None
    stop_tm: Optional[List[float]] = None
    wf1_ct: Optional[List[int]] = None
    wf1_tm: Optional[List[float]] = None
    wf2_ct: Optional[List[int]] = None
    wf2_tm: Optional[List[float]] = None
    lh_ct: Optional[List[int]] = None
    lh_tm: Optional[List[float]] = None


class StopEventOut(_Base):
    id: int
    machine_id: int
    mac_name: Optional[str] = None
    shift_id: Optional[str] = None
    day: str
    stop_time: int
    run_time: int
    raw_code: str
    fixed: bool
    stop_start: Optional[datetime] = None
    stop_end: Optional[datetime] = None
    duration_min: Optional[float] = None


class PeriodRowOut(_Base):
    period: str
    key: str
    mac_name: str
    mac_type: str
    style: Optional[str] = None
    beam: Optional[str] = None
    ubeam: Optional[str] = None
    seisan: List[float] = []
    off_prod: List[float] = []
    production: float = 0.0
    run_tm: float = 0.0
    stop_ttm: float = 0.0
    effic: float = 0.0
    rpm: float = 0.0
    total_ct: int = 0
    stop_ct: List[int] = []
    stop_tm: List[float] = []
    wf1_ct: List[int] = []
    wf1_tm: List[float] = []
    wf2_ct: List[int] = []
    wf2_tm: List[float] = []
    lh_ct: List[int] = []
    lh_tm: List[float] = []


class OperatorDailyOut(_Base):
    id: int
    machine_id: int
    mac_name: Optional[str] = None
    operator_id: int
    day: str
    start_time: Optional[datetime] = None
    seisan: Optional[dict] = None
    run_tm: Optional[int] = None
    stop_ttm: Optional[int] = None
    s_ct: Optional[List[int]] = None
    s_tm: Optional[List[int]] = None
    raw_line: Optional[str] = None


def serialize(obj: Any, schema: type, mac_name: Optional[str] = None) -> Any:
    """Converte um ORM obj (opcionalmente + mac_name do join) no schema."""
    from sqlalchemy import inspect

    data = {attr.key: getattr(obj, attr.key) for attr in inspect(obj).mapper.column_attrs}
    if mac_name is not None:
        data["mac_name"] = mac_name
    return schema.model_validate(data)
