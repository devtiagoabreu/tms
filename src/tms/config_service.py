"""Configuração e edição (Fase 4).

Leitura/escrita das configurações antes guardadas em arquivos pelo legado:

- `setting/ipaddress.txt`    → tabela `ip_ranges` (faixas de IP);
- `set/style_mst.txt`        → tabela `styles` (nome/densidade/comprimento);
- `set/system_set.txt`       → `shift_schedules` (escala de turnos);
- `setting/selitem.txt`      → `report_prefs` (itens de relatório);
- demais chaves (language, scanner_ip, memcard…) → tabela `settings`.
"""

from __future__ import annotations

import copy
from typing import Dict, List, Optional, Sequence, Tuple

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from tms.models.masters import IpRange, ReportPref, Setting, ShiftSchedule, Style

# ---------------------------------------------------------------- settings --

def get_setting(db: Session, key: str, default: Optional[str] = None) -> Optional[str]:
    row = db.get(Setting, key)
    return row.value if row is not None else default


def set_setting(db: Session, key: str, value: Optional[str]) -> None:
    """Define (ou apaga, se `value is None`) uma chave de `settings`."""
    row = db.get(Setting, key)
    if value is None:
        if row is not None:
            db.delete(row)
            db.flush()
        return
    if row is None:
        db.add(Setting(key=key, value=value))
    else:
        row.value = value


def all_settings(db: Session) -> Dict[str, Optional[str]]:
    return {row.key: row.value for row in db.execute(select(Setting)).scalars()}


# --------------------------------------------------------------- ip_ranges --

OCTET_MAX = 255

IpTuple = Tuple[int, int, int, int, int]


def _int_tokens(line: str) -> Optional[List[int]]:
    parts = line.replace(",", " ").split()
    if len(parts) == 4:
        parts = parts + [parts[3]]
    if len(parts) != 5:
        return None
    try:
        return [int(p) for p in parts]
    except ValueError:
        return None


def parse_ip_ranges(text: str) -> List[IpTuple]:
    ranges: List[IpTuple] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        nums = _int_tokens(line)
        if nums is None or any(n < 0 or n > OCTET_MAX for n in nums):
            continue
        a, b, c, start, end = nums
        if start > end:
            start, end = end, start
        ranges.append((a, b, c, start, end))
    return ranges


def merge_ip_ranges(ranges: Sequence[IpTuple]) -> List[IpTuple]:
    """Une faixas da mesma sub-rede que se tocam/sobrepõem (como ipset2.cgi)."""
    merged: List[IpTuple] = []
    for item in sorted(set(ranges)):
        a, b, c, start, end = item
        if merged:
            pa, pb, pc, pstart, pend = merged[-1]
            if (pa, pb, pc) == (a, b, c) and pend + 1 >= start:
                if end > pend:
                    merged[-1] = (pa, pb, pc, pstart, end)
                continue
        merged.append(item)
    return merged


def format_ip_ranges(ranges: Sequence[IpTuple]) -> str:
    return "".join(f"{a} {b} {c} {start} {end}\n" for a, b, c, start, end in ranges)


def expand_ip_ranges(ranges: Sequence[IpTuple]) -> List[str]:
    ips: List[str] = []
    for a, b, c, start, end in ranges:
        ips.extend(f"{a}.{b}.{c}.{i}" for i in range(start, end + 1))
    return ips


def get_ip_ranges(db: Session) -> List[IpTuple]:
    rows = db.execute(
        select(IpRange).order_by(IpRange.a, IpRange.b, IpRange.c, IpRange.start)
    ).scalars()
    return [(r.a, r.b, r.c, r.start, r.end) for r in rows]


def replace_ip_ranges(db: Session, text: str) -> List[IpTuple]:
    ranges = merge_ip_ranges(parse_ip_ranges(text))
    db.execute(delete(IpRange))
    for a, b, c, start, end in ranges:
        db.add(IpRange(a=a, b=b, c=c, start=start, end=end))
    db.flush()
    return ranges


# ------------------------------------------------------------------- styles --

def parse_styles(text: str) -> List[dict]:
    styles: List[dict] = []
    for raw in text.splitlines():
        if not raw.strip():
            continue
        parts = raw.split("\t")
        name = parts[0].strip()
        if not name:
            continue
        density = parts[1].strip() if len(parts) > 1 else ""
        doff: Optional[int] = None
        if len(parts) > 2 and parts[2].strip():
            try:
                doff = int(parts[2].strip())
            except ValueError:
                doff = None
        styles.append({"name": name, "density": density, "doff_len": doff})
    return styles


def format_styles(styles: Sequence[dict]) -> str:
    lines = []
    for style in styles:
        doff = "" if style.get("doff_len") is None else str(style["doff_len"])
        lines.append(f"{style['name']}\t{style.get('density') or ''}\t{doff}")
    return "\n".join(lines) + ("\n" if lines else "")


def get_styles(db: Session) -> List[dict]:
    rows = db.execute(select(Style).order_by(Style.name)).scalars()
    return [
        {"name": r.name, "density": r.density, "doff_len": r.doff_len,
         "beam_type": r.beam_type, "unit": r.unit}
        for r in rows
    ]


def replace_styles(db: Session, text: str) -> List[dict]:
    styles = parse_styles(text)
    existing = {r.name: r for r in db.execute(select(Style)).scalars()}
    seen = set()
    for style in styles:
        seen.add(style["name"])
        row = existing.get(style["name"])
        if row is None:
            db.add(Style(name=style["name"], density=style["density"], doff_len=style["doff_len"]))
        else:
            row.density = style["density"]
            row.doff_len = style["doff_len"]
    for name, row in existing.items():
        if name not in seen:
            db.delete(row)
    db.flush()
    return styles


# --------------------------------------------------------- shift_schedule ---

SHIFT_DEFAULTS = {"is_week": 0, "simple": [3, "08:00", "16:00", "23:59"], "week": {}}


def _schedule_values(tokens: Sequence[str]) -> List:
    if not tokens:
        return []
    count = int(tokens[0])
    return [count] + list(tokens[1 : 1 + 2 * count])


def parse_shift_schedule(text: str) -> dict:
    schedule = {"is_week": 0, "simple": [], "week": {}}
    for raw in text.splitlines():
        parts = raw.split()
        if not parts:
            continue
        if parts[0] == "shift_schedule_is_week" and len(parts) >= 2:
            schedule["is_week"] = int(parts[1])
        elif parts[0] == "shift_schedule_simple":
            schedule["simple"] = _schedule_values(parts[1:])
        elif parts[0] == "shift_schedule_week" and len(parts) >= 2:
            schedule["week"][str(int(parts[1]))] = _schedule_values(parts[2:])
    return schedule


def format_shift_schedule(schedule: dict) -> str:
    lines = [f"shift_schedule_is_week {int(schedule.get('is_week', 0))}"]
    simple = schedule.get("simple") or []
    lines.append("shift_schedule_simple " + " ".join(str(v) for v in simple))
    week = schedule.get("week") or {}
    for day in range(7):
        values = week.get(str(day))
        if values:
            lines.append(f"shift_schedule_week {day} " + " ".join(str(v) for v in values))
    return "\n".join(lines) + "\n"


def get_shift_schedule(db: Session, code: str = "default") -> dict:
    row = db.execute(select(ShiftSchedule).where(ShiftSchedule.code == code)).scalars().first()
    if row is None:
        return copy.deepcopy(SHIFT_DEFAULTS)
    schedule = copy.deepcopy(SHIFT_DEFAULTS)
    schedule["is_week"] = row.shift_mode
    if row.simple:
        schedule["simple"] = _schedule_values(row.simple.split())
    if row.schedule_json:
        schedule["week"] = row.schedule_json.get("week", {})
    return schedule


def replace_shift_schedule(db: Session, text: str, code: str = "default") -> dict:
    schedule = parse_shift_schedule(text)
    row = db.execute(select(ShiftSchedule).where(ShiftSchedule.code == code)).scalars().first()
    simple = " ".join(str(v) for v in schedule["simple"])
    if row is None:
        db.add(
            ShiftSchedule(
                code=code,
                shift_mode=schedule["is_week"],
                simple=simple,
                schedule_json={"week": schedule["week"]},
            )
        )
    else:
        row.shift_mode = schedule["is_week"]
        row.simple = simple
        row.schedule_json = {"week": schedule["week"]}
    db.flush()
    return schedule


# ----------------------------------------------------------- report prefs ---

SELITEM_ITEM2 = ("top_beam", "beam", "rpm", "effic", "run", "stop", "product")
SELITEM_ITEM = (
    "warp_top", "warp", "false", "leno_l", "leno_r", "weft",
    "warp_out", "doffing", "manual", "power_off", "other",
)
SELITEM_ITEM3 = ("cc_front", "cc_rear", "leno")
SELITEM_DETAIL = ("wf1", "wf2", "lh")

SELITEM_DEFAULTS = {
    "item2": [0, 0, 1, 1, 1, 1, 1],
    "item": [0, 1, 0, 1, 1, 1, 0, 0, 0, 0, 0],
    "item3": [0, 0, 0],
    "detail": [1, 0, 0],
    "color": [1, 1, 0, 0, 0, 0],
    "beam_type": 1,
    "unit": 0,
    "period": "shift",
    "week": 0,
    "effic": 90,
    "run_tm": 30,
    "expire": 26,
}

_LIST_KEYS = {"item2": 7, "item": 11, "item3": 3, "detail": 3, "color": 6}
_INT_KEYS = {"beam_type", "unit", "week", "effic", "run_tm", "expire"}


def _as_int_list(values: Sequence, size: int) -> List[int]:
    out = [int(v) for v in values[:size]]
    return out + [0] * (size - len(out))


def parse_report_prefs(text: str) -> dict:
    prefs = copy.deepcopy(SELITEM_DEFAULTS)
    for raw in text.splitlines():
        parts = raw.split()
        if not parts:
            continue
        key = parts[0]
        if key in _LIST_KEYS:
            prefs[key] = _as_int_list(parts[1:], _LIST_KEYS[key])
        elif key in _INT_KEYS:
            try:
                prefs[key] = int(parts[1])
            except (IndexError, ValueError):
                pass
        elif key == "period" and len(parts) > 1:
            prefs[key] = parts[1]
    return prefs


def format_report_prefs(prefs: dict) -> str:
    prefs = _normalize_prefs(prefs)
    lines = ["Version 3.00"]
    for key in ("item2", "item"):
        lines.append(f"{key:<10}" + " ".join(str(v) for v in prefs[key]))
    for key in ("item3", "detail", "color"):
        lines.append(f"{key:<10}" + " ".join(str(v) for v in prefs[key]))
    lines.append(f"beam_type {prefs['beam_type']}")
    lines.append(f"unit      {prefs['unit']}")
    lines.append(f"period    {prefs['period']}")
    lines.append(f"week      {prefs['week']}")
    lines.append(f"effic     {prefs['effic']:03d}")
    lines.append(f"run_tm    {prefs['run_tm']:03d}")
    lines.append(f"expire    {prefs['expire']}")
    return "\n".join(lines) + "\n"


def _normalize_prefs(prefs: dict) -> dict:
    normalized = copy.deepcopy(SELITEM_DEFAULTS)
    for key, size in _LIST_KEYS.items():
        if key in prefs:
            normalized[key] = _as_int_list(prefs[key], size)
    for key in _INT_KEYS:
        if key in prefs:
            normalized[key] = int(prefs[key])
    if prefs.get("period"):
        normalized["period"] = str(prefs["period"])
    return normalized


def get_report_prefs(db: Session) -> dict:
    prefs = copy.deepcopy(SELITEM_DEFAULTS)
    for row in db.execute(select(ReportPref)).scalars():
        if row.key in _LIST_KEYS:
            prefs[row.key] = _as_int_list(row.value.split(), _LIST_KEYS[row.key])
        elif row.key in _INT_KEYS:
            try:
                prefs[row.key] = int(row.value)
            except ValueError:
                pass
        elif row.key == "period":
            prefs[row.key] = row.value
    return prefs


def replace_report_prefs(db: Session, prefs) -> dict:
    if isinstance(prefs, str):
        prefs = parse_report_prefs(prefs)
    normalized = _normalize_prefs(prefs)
    db.execute(delete(ReportPref))
    for key, value in normalized.items():
        if isinstance(value, list):
            text = " ".join(str(v) for v in value)
        else:
            text = str(value)
        db.add(ReportPref(key=key, value=text))
    db.flush()
    return normalized
