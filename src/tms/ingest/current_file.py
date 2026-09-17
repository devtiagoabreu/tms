"""Parser de `current/current.txt` e `current/setting.txt`.

Uma linha por tear, no formato ``key value`` separado por vírgulas
(ver docs/migracao/02-modelo-de-dados.md §1–2).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

from tms.ingest._common import (
    parse_int_list,
    parse_kv_line,
    parse_timestamp,
    to_int,
)


@dataclass
class CurrentRecord:
    """Snapshot de um tear (linha de `current.txt`)."""

    mac_name: str = ""
    mac_type: str = ""
    ip_addr: str = ""
    shift: str = ""
    get_time: Optional[datetime] = None
    sys_time: Optional[datetime] = None
    rtc_time: Optional[datetime] = None
    style: str = ""
    beam: str = ""
    ubeam: str = ""
    count_unit: str = ""
    s_beam: List[int] = field(default_factory=list)
    r_beam: List[int] = field(default_factory=list)
    s_ubeam: List[int] = field(default_factory=list)
    r_ubeam: List[int] = field(default_factory=list)
    cloth_len: List[int] = field(default_factory=list)
    cut_len: List[int] = field(default_factory=list)
    doff_fcst: int = 0
    wout_fcst: int = 0
    uwout_fcst: int = 0
    extra: Dict[str, str] = field(default_factory=dict)

    @property
    def clock_diff_seconds(self) -> Optional[float]:
        """Diferença `sys_time - rtc_time` em segundos (relógio da máquina)."""
        if self.sys_time is None or self.rtc_time is None:
            return None
        return (self.sys_time - self.rtc_time).total_seconds()


@dataclass
class SettingRecord(CurrentRecord):
    """`setting.txt`: snapshot + configuração de turnos.

    `SIMPLE`/`DAY_n` são listas cruas: número de turnos seguido de pares
    ``HH:MM``; ``-1:-1`` significa ausente.
    """

    shift_mode: int = 0
    simple: List[str] = field(default_factory=list)
    days: Dict[int, List[str]] = field(default_factory=dict)
    names: Dict[int, str] = field(default_factory=dict)
    day_start_time: str = ""


def _base_fields(kv: Dict[str, str]) -> CurrentRecord:
    return CurrentRecord(
        mac_name=kv.get("mac_name", ""),
        mac_type=kv.get("mac_type", ""),
        ip_addr=kv.get("ip_addr", ""),
        shift=kv.get("shift", ""),
        get_time=parse_timestamp(kv.get("get_time", "").split()),
        sys_time=parse_timestamp(kv.get("sys_time", "").split()),
        rtc_time=parse_timestamp(kv.get("rtc_time", "").split()),
        style=kv.get("style", ""),
        beam=kv.get("beam", ""),
        ubeam=kv.get("ubeam", ""),
        count_unit=kv.get("count_unit", ""),
        s_beam=parse_int_list(kv.get("s_beam", "")),
        r_beam=parse_int_list(kv.get("r_beam", "")),
        s_ubeam=parse_int_list(kv.get("s_ubeam", "")),
        r_ubeam=parse_int_list(kv.get("r_ubeam", "")),
        cloth_len=parse_int_list(kv.get("cloth_len", "")),
        cut_len=parse_int_list(kv.get("cut_len", "")),
        doff_fcst=to_int(kv.get("doff_fcst", "")),
        wout_fcst=to_int(kv.get("wout_fcst", "")),
        uwout_fcst=to_int(kv.get("uwout_fcst", "")),
    )


def parse_current_line(line: str) -> Optional[CurrentRecord]:
    if not line.strip().strip(","):
        return None
    return _base_fields(parse_kv_line(line))


def parse_current_file(text: str) -> List[CurrentRecord]:
    records = []
    for line in text.splitlines():
        record = parse_current_line(line)
        if record is not None:
            records.append(record)
    return records


def parse_setting_line(line: str) -> Optional[SettingRecord]:
    if not line.strip().strip(","):
        return None
    kv = parse_kv_line(line)
    base = _base_fields(kv)
    record = SettingRecord(**vars(base))
    record.shift_mode = to_int(kv.get("SHIFT_MODE", ""))
    record.simple = kv.get("SIMPLE", "").split()
    for day in range(7):
        key = f"DAY_{day}"
        if key in kv:
            record.days[day] = kv[key].split()
    for slot in range(6):
        key = f"NAME_{slot}"
        if key in kv:
            record.names[slot] = kv[key]
    record.day_start_time = kv.get("DAY_START_TIME", "")
    return record


def parse_setting_file(text: str) -> List[SettingRecord]:
    records = []
    for line in text.splitlines():
        record = parse_setting_line(line)
        if record is not None:
            records.append(record)
    return records
