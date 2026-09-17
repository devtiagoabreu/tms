"""Parser de `loom/<mac>.txt` — registro diário de um tear.

O arquivo é dividido em secções marcadas (ver
docs/migracao/02-modelo-de-dados.md §3 e 04-coleta-dados-looms.md):

- cabeçalho `get_time <y m d w H M S>`
- `JAT710-TMS-DATA current`    — estado atual (`#end_of_data` encerra)
- `JAT710-TMS-DATA stop_history` — eventos `MH_d<N>_h<H>_history`
- `JAT700-MCARD-DATA file_info`  — machine/style/beam/top_beam
- `JAT700-MCARD-DATA moni_monitor` — contadores por turno/dia (`MJ_t_s*`, `PM_t_*`)
- `JAT700-MCARD-DATA shift`      — configuração de turnos
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, time
from typing import Dict, List, Optional

from tms.ingest._common import (
    parse_int_list,
    parse_kv_line,
    parse_timestamp,
    split_kv,
    to_int,
    unquote,
)

_MARKERS = (
    (("-TMS-DATA current"), "current"),
    (("-TMS-DATA stop_history"), "stop_history"),
    (("-MCARD-DATA file_info"), "file_info"),
    (("-MCARD-DATA moni_monitor"), "moni_monitor"),
    (("-MCARD-DATA shift"), "shift"),
)

_DAY_RE = re.compile(r"^(DAY|NAME)\s+(\d+)\s+(.*)$")
_HISTORY_RE = re.compile(r"^MH_d(\d+)_h(\d+)_history$")
_DAY_TM_RE = re.compile(r"^MH_d(\d+)_tm$")


@dataclass
class LoomStopEvent:
    """Evento do histórico de paradas embutido no `loom/<mac>.txt`."""

    day: int
    hour: int
    start: Optional[time]
    end: Optional[time]
    code: str


@dataclass
class MoniShift:
    """Bloco `MJ_t_sN_*` (turno atual/próximo) ou `PM_t_pN_*` (análise de pick)."""

    seisan: List[int] = field(default_factory=list)
    rt: int = 0
    sc: List[int] = field(default_factory=list)
    st: List[int] = field(default_factory=list)
    to: int = 0
    tm: Optional[datetime] = None
    sn: str = ""
    bn_b: str = ""
    bn_t: str = ""
    bt_use: int = 0
    ss: List[int] = field(default_factory=list)
    en: List[int] = field(default_factory=list)
    op: str = ""
    extra: Dict[str, str] = field(default_factory=dict)

    @property
    def run_min(self) -> float:
        return self.rt / 60.0


@dataclass
class LoomFile:
    """Conteúdo interpretado de `loom/<mac>.txt`."""

    get_time: Optional[datetime] = None
    ip_addr: str = ""
    mac_name: str = ""
    mac_type: str = ""
    sys_time: Optional[datetime] = None
    rtc_time: Optional[datetime] = None
    shift: str = ""
    style: str = ""
    beam: str = ""
    ubeam: str = ""
    ubeam_use: int = 0
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
    stop_events: List[LoomStopEvent] = field(default_factory=list)
    day_start: Dict[int, datetime] = field(default_factory=dict)
    file_info: Dict[str, str] = field(default_factory=dict)
    monitor: Dict[str, str] = field(default_factory=dict)
    current_shift: Optional[MoniShift] = None
    next_shift: Optional[MoniShift] = None
    pick: Optional[MoniShift] = None
    pick_now_p: int = 0
    shift_mode: int = 0
    simple: List[str] = field(default_factory=list)
    days: Dict[int, List[str]] = field(default_factory=dict)
    names: Dict[int, str] = field(default_factory=dict)
    day_start_time: str = ""

    @property
    def clock_diff_seconds(self) -> Optional[float]:
        if self.sys_time is None or self.rtc_time is None:
            return None
        return (self.sys_time - self.rtc_time).total_seconds()


def _parse_time_token(token: str) -> Optional[time]:
    token = token.strip()
    if not token or token == "-":
        return None
    parts = token.split(":")
    if len(parts) != 3:
        return None
    try:
        return time(int(parts[0]), int(parts[1]), int(parts[2]))
    except ValueError:
        return None


def _split_sections(text: str):
    """Gera `(nome, linhas)` para cada secção marcada do arquivo."""
    current_name: Optional[str] = None
    current_lines: List[str] = []
    for raw in text.splitlines():
        stripped = raw.strip()
        matched = None
        for needle, name in _MARKERS:
            if needle in stripped:
                matched = name
                break
        if matched is not None:
            if current_name is not None:
                yield current_name, current_lines
            current_name, current_lines = matched, []
            continue
        if current_name is not None and stripped != "#end_of_data":
            current_lines.append(raw)
    if current_name is not None:
        yield current_name, current_lines


def _parse_moni_group(monitor: Dict[str, str], prefix: str) -> Optional[MoniShift]:
    if f"{prefix}_seisan" not in monitor:
        return None
    return MoniShift(
        seisan=parse_int_list(monitor.get(f"{prefix}_seisan", "")),
        rt=to_int(monitor.get(f"{prefix}_rt", "")),
        sc=parse_int_list(monitor.get(f"{prefix}_sc", "")),
        st=parse_int_list(monitor.get(f"{prefix}_st", "")),
        to=to_int(monitor.get(f"{prefix}_to", "")),
        tm=parse_timestamp(monitor.get(f"{prefix}_tm", "").split()),
        sn=monitor.get(f"{prefix}_sn", ""),
        bn_b=monitor.get(f"{prefix}_bn_b", ""),
        bn_t=monitor.get(f"{prefix}_bn_t", ""),
        bt_use=to_int(monitor.get(f"{prefix}_bt_use", "")),
        ss=[to_int(monitor.get(f"{prefix}_ss{i}", "")) for i in range(3)],
        en=[to_int(monitor.get(f"{prefix}_en{i}", "")) for i in range(3)],
        op=monitor.get(f"{prefix}_op", ""),
    )


def parse_loom_file(text: str) -> LoomFile:
    lines = text.splitlines()
    result = LoomFile()

    if lines:
        key, value = split_kv(lines[0])
        if key == "get_time":
            result.get_time = parse_timestamp(value.split())

    for name, body in _split_sections(text):
        if name == "current":
            kv: Dict[str, str] = {}
            for line in body:
                k, v = split_kv(line)
                if k:
                    kv[k] = v
            result.ip_addr = kv.get("ip_addr", "")
            result.mac_name = kv.get("mac_name", "")
            result.sys_time = parse_timestamp(kv.get("sys_time", "").split())
            result.rtc_time = parse_timestamp(kv.get("rtc_time", "").split())
            result.shift = kv.get("shift", "")
            result.style = kv.get("style", "")
            result.beam = kv.get("beam", "")
            result.ubeam = kv.get("ubeam", "")
            result.ubeam_use = to_int(kv.get("ubeam_use", ""))
            result.count_unit = kv.get("count_unit", "")
            result.s_beam = parse_int_list(kv.get("s_beam", ""))
            result.r_beam = parse_int_list(kv.get("r_beam", ""))
            result.s_ubeam = parse_int_list(kv.get("s_ubeam", ""))
            result.r_ubeam = parse_int_list(kv.get("r_ubeam", ""))
            result.cloth_len = parse_int_list(kv.get("cloth_len", ""))
            result.cut_len = parse_int_list(kv.get("cut_len", ""))
            result.doff_fcst = to_int(kv.get("doff_fcst", ""))
            result.wout_fcst = to_int(kv.get("wout_fcst", ""))
            result.uwout_fcst = to_int(kv.get("uwout_fcst", ""))

        elif name == "stop_history":
            for line in body:
                key, value = split_kv(line)
                if not key:
                    continue
                match = _HISTORY_RE.match(key)
                if match:
                    tokens = value.split()
                    start = _parse_time_token(tokens[0]) if len(tokens) > 0 else None
                    end = _parse_time_token(tokens[1]) if len(tokens) > 1 else None
                    code = tokens[2] if len(tokens) > 2 else ""
                    result.stop_events.append(
                        LoomStopEvent(
                            day=int(match.group(1)),
                            hour=int(match.group(2)),
                            start=start,
                            end=end,
                            code=code,
                        )
                    )
                    continue
                match = _DAY_TM_RE.match(key)
                if match:
                    result.day_start[int(match.group(1))] = parse_timestamp(value.split())

        elif name == "file_info":
            info: Dict[str, str] = {}
            for line in body:
                key, value = split_kv(line)
                if key:
                    info[key] = unquote(value)
            result.file_info = info

        elif name == "moni_monitor":
            monitor: Dict[str, str] = {}
            for line in body:
                key, value = split_kv(line)
                if key:
                    monitor[key] = value
            result.monitor = monitor
            sb = monitor.get("MJ_current_sb", "").split()
            if len(sb) >= 2:
                result.style, result.beam = sb[0], sb[1]
                if len(sb) >= 3 and sb[2] != "*":
                    result.ubeam = sb[2]
            result.current_shift = _parse_moni_group(monitor, "MJ_t_s0")
            result.next_shift = _parse_moni_group(monitor, "MJ_t_s1")
            result.pick = _parse_moni_group(monitor, "PM_t_p5")
            result.pick_now_p = to_int(monitor.get("PM_i_now_p", ""))

        elif name == "shift":
            for line in body:
                match = _DAY_RE.match(line.strip())
                if match:
                    kind, index, value = match.groups()
                    if kind == "DAY":
                        result.days[int(index)] = value.split()
                    else:
                        result.names[int(index)] = unquote(value)
                    continue
                key, value = split_kv(line)
                if key == "SHIFT_MODE":
                    result.shift_mode = to_int(value)
                elif key == "SIMPLE":
                    result.simple = value.split()
                elif key == "DAY_START_TIME":
                    result.day_start_time = value

    detected = result.mac_type or ""
    for needle, mac_type in (("JAT710", "JAT710"), ("JAT700", "JAT700"), ("LW700", "LWT710"), ("LWT710", "LWT710")):
        if needle in text:
            detected = mac_type
            break
    result.mac_type = detected
    return result
