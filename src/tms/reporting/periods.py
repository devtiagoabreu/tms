"""Agregação de período (dia/semana/mês) a partir dos registros brutos.

Espelha `common/TMSDATAfinal.pm`:

- agrupa por ``(mac_name, mac_type, style, beam, ubeam)`` (em modo turno o
  operador é "dummy", ou seja, ignorado);
- soma ``seisan``/``off_prod`` (décimos), ``run_tm``/``stop_ttm`` (segundos) e
  os arrays crus de parada, **sem** tirar médias;
- recomputa EFFIC/RPM a partir das somas (nunca média de taxas);
- filtra cada registro por ``run_tm >= min_run_tm`` (minutos) e
  ``effic >= min_effic`` **antes** de agregar;
- semana ancorada no início configurável (0 = domingo, como o legado), não ISO.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Iterable, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from tms.core.formulas import (
    UNIT_PICK,
    effic,
    production,
    rpm_from_agg,
    shiftreport_total,
)
from tms.core.stopcodes import get_detail_stop
from tms.ingest.shift_file import parse_shift_line
from tms.models.masters import Machine
from tms.models.runtime import DailyRaw

# 0 = domingo (default do selitem legado). 1 = segunda, ...
WEEK_START = 0

PERIODS = ("day", "week", "month")

_RAW_LEN = {"JAT": 40, "LWT": 31}


@dataclass(frozen=True)
class RawRecord:
    """Registro bruto por tear/dia/turno (visão de `daily_raw`)."""

    mac_name: str
    mac_type: str
    style: Optional[str]
    beam: Optional[str]
    ubeam: Optional[str]
    seisan: tuple[int, ...] = ()  # décimos
    off_prod: tuple[int, ...] = ()
    run_tm: int = 0  # segundos
    stop_ttm: int = 0  # segundos
    s_ct: tuple[int, ...] = ()
    s_tm: tuple[int, ...] = ()
    day: Optional[str] = None  # YYYY.MM.DD (para particionar o período)

    def effic(self) -> float:
        return effic(self.run_tm, self.stop_ttm)


@dataclass
class PeriodRow:
    """Linha agregada pronta para relatório/CSV."""

    period: str
    key: str
    mac_name: str
    mac_type: str
    style: Optional[str]
    beam: Optional[str]
    ubeam: Optional[str]
    seisan: list[float] = field(default_factory=list)  # /10
    off_prod: list[float] = field(default_factory=list)  # /10
    run_tm: float = 0.0  # minutos
    stop_ttm: float = 0.0  # minutos
    effic: float = 0.0
    rpm: float = 0.0
    stop_ct: list[int] = field(default_factory=list)  # 12
    stop_tm: list[float] = field(default_factory=list)  # 12 (min)
    wf1_ct: list[int] = field(default_factory=list)
    wf1_tm: list[float] = field(default_factory=list)
    wf2_ct: list[int] = field(default_factory=list)
    wf2_tm: list[float] = field(default_factory=list)
    lh_ct: list[int] = field(default_factory=list)
    lh_tm: list[float] = field(default_factory=list)

    def production(self, unit: int = UNIT_PICK) -> float:
        return production(self.seisan, self.off_prod, unit)

    def total_ct(self, beam_type: int = 1) -> int:
        return shiftreport_total(self.stop_ct, beam_type)


def month_key(day: str) -> str:
    """``2025.10.01`` → ``2025.10``."""
    return ".".join(day.split(".")[:2])


def week_key(day: str, week_start: int = WEEK_START) -> str:
    """Início da semana de ``day`` (YYYY.MM.DD), ancorado em ``week_start``."""
    y, m, d = (int(p) for p in day.split(".")[:3])
    dt = date(y, m, d)
    wday = (dt.weekday() + 1) % 7  # Python: seg=0 → perl/legado: dom=0
    offset = (wday - week_start) % 7
    return (dt - timedelta(days=offset)).strftime("%Y.%m.%d")


def period_key(period: str, day: str, week_start: int = WEEK_START) -> str:
    if period == "day":
        return day
    if period == "week":
        return week_key(day, week_start)
    if period == "month":
        return month_key(day)
    raise ValueError(f"período inválido: {period}")


def _padded(values: Iterable[int], mac_type: str) -> list[int]:
    size = _RAW_LEN.get(mac_type.upper(), 40)
    out = list(values)[:size]
    out += [0] * (size - len(out))
    return out


def _sum_padded(acc: list[int], values: Iterable[int], mac_type: str) -> list[int]:
    src = _padded(values, mac_type)
    for i, v in enumerate(src):
        acc[i] += v
    return acc


@dataclass
class _Acc:
    mac_name: str
    mac_type: str
    style: Optional[str]
    beam: Optional[str]
    ubeam: Optional[str]
    seisan: list[int] = field(default_factory=lambda: [0, 0, 0, 0])
    off_prod: list[int] = field(default_factory=lambda: [0, 0, 0, 0])
    run_tm: int = 0
    stop_ttm: int = 0
    s_ct: list[int] = field(default_factory=list)
    s_tm: list[int] = field(default_factory=list)


def aggregate_records(
    records: Iterable[RawRecord],
    period: str,
    *,
    day_of: dict[int, str] | None = None,
    week_start: int = WEEK_START,
    min_run_tm: float = 0.0,
    min_effic: float = 0.0,
    unit: int = UNIT_PICK,
    beam_type: int = 1,
) -> list[PeriodRow]:
    """Agrega registros brutos por período.

    ``day_of`` mapeia ``id(record)`` → ``YYYY.MM.DD`` (necessário se o registro
    não carrega a data; sem ele usa-se o atributo ``day``).
    """
    accs: dict[tuple, _Acc] = {}
    for rec in records:
        if rec.run_tm < min_run_tm * 60:
            continue
        if min_effic and rec.effic() < min_effic:
            continue
        day = (day_of or {}).get(id(rec)) or rec.day
        if day is None:
            raise ValueError("registro sem data; informe day_of")
        key = (period_key(period, day, week_start), rec.mac_name, rec.mac_type,
               rec.style, rec.beam, rec.ubeam)
        acc = accs.get(key)
        if acc is None:
            acc = _Acc(rec.mac_name, rec.mac_type, rec.style, rec.beam, rec.ubeam)
            acc.s_ct = [0] * _RAW_LEN.get(rec.mac_type.upper(), 40)
            acc.s_tm = [0] * _RAW_LEN.get(rec.mac_type.upper(), 40)
            accs[key] = acc
        for i, v in enumerate(rec.seisan[:4]):
            acc.seisan[i] += v
        for i, v in enumerate(rec.off_prod[:4]):
            acc.off_prod[i] += v
        acc.run_tm += rec.run_tm
        acc.stop_ttm += rec.stop_ttm
        _sum_padded(acc.s_ct, rec.s_ct, rec.mac_type)
        _sum_padded(acc.s_tm, rec.s_tm, rec.mac_type)

    rows: list[PeriodRow] = []
    for key, acc in sorted(accs.items(), key=lambda kv: (kv[0][0], kv[0][1])):
        detail_ct = get_detail_stop(acc.mac_type, acc.s_ct)
        detail_tm = get_detail_stop(acc.mac_type, acc.s_tm)
        run_min = round(acc.run_tm / 60.0, 3)
        stop_min = round(acc.stop_ttm / 60.0, 3)
        seisan_final = [round(v / 10.0, 1) for v in acc.seisan]
        off_final = [round(v / 10.0, 1) for v in acc.off_prod]
        rows.append(
            PeriodRow(
                period=period,
                key=key[0],
                mac_name=acc.mac_name,
                mac_type=acc.mac_type,
                style=acc.style,
                beam=acc.beam,
                ubeam=acc.ubeam,
                seisan=seisan_final,
                off_prod=off_final,
                run_tm=run_min,
                stop_ttm=stop_min,
                effic=effic(acc.run_tm, acc.stop_ttm),
                rpm=rpm_from_agg(seisan_final[0] if seisan_final else 0.0, run_min),
                stop_ct=detail_ct["stop_ct"],
                stop_tm=[round(v / 60.0, 3) for v in detail_tm["stop_ct"]],
                wf1_ct=detail_ct["wf1"],
                wf1_tm=[round(v / 60.0, 3) for v in detail_tm["wf1"]],
                wf2_ct=detail_ct["wf2"],
                wf2_tm=[round(v / 60.0, 3) for v in detail_tm["wf2"]],
                lh_ct=detail_ct["lh"],
                lh_tm=[round(v / 60.0, 3) for v in detail_tm["lh"]],
            )
        )
    return rows


def _as_record(row: DailyRaw, mac_name: str, mac_type: str) -> RawRecord:
    seisan = (row.seisan or {}).get("seisan", [])
    off_prod = (row.seisan or {}).get("off_prod", [])
    style = beam = ubeam = None
    if row.raw_line:
        parsed = parse_shift_line(row.raw_line)
        if parsed is not None:
            style, beam, ubeam = parsed.style, parsed.beam, parsed.ubeam
    return RawRecord(
        mac_name=mac_name,
        mac_type=mac_type,
        style=style or None,
        beam=beam or None,
        ubeam=ubeam or None,
        seisan=tuple(seisan),
        off_prod=tuple(off_prod),
        run_tm=row.run_tm or 0,
        stop_ttm=row.stop_ttm or 0,
        s_ct=tuple(row.s_ct or []),
        s_tm=tuple(row.s_tm or []),
        day=row.day,
    )


def load_records(
    db: Session,
    *,
    day_from: Optional[str] = None,
    day_to: Optional[str] = None,
    mac_name: Optional[str] = None,
) -> list[RawRecord]:
    """Carrega `daily_raw` (join `machines`) como `RawRecord`s com ``day``."""
    stmt = select(DailyRaw, Machine.mac_name, Machine.mac_type).join(
        Machine, Machine.id == DailyRaw.machine_id
    )
    if mac_name:
        stmt = stmt.where(Machine.mac_name == mac_name)
    if day_from:
        stmt = stmt.where(DailyRaw.day >= day_from)
    if day_to:
        stmt = stmt.where(DailyRaw.day <= day_to)
    stmt = stmt.order_by(DailyRaw.day, DailyRaw.shift_id, Machine.mac_name)

    records: list[RawRecord] = []
    for row, name, mac_type in db.execute(stmt):
        records.append(_as_record(row, name, mac_type))
    return records


def report(
    db: Session,
    period: str,
    *,
    key: Optional[str] = None,
    day_from: Optional[str] = None,
    day_to: Optional[str] = None,
    mac_name: Optional[str] = None,
    week_start: int = WEEK_START,
    min_run_tm: float = 0.0,
    min_effic: float = 0.0,
    unit: int = UNIT_PICK,
    beam_type: int = 1,
) -> list[PeriodRow]:
    """Agrega `daily_raw` no período pedido (filtra por `key`/data/tear)."""
    if period not in PERIODS:
        raise ValueError(f"período inválido: {period}")
    records = load_records(db, day_from=day_from, day_to=day_to, mac_name=mac_name)
    rows = aggregate_records(
        records,
        period,
        week_start=week_start,
        min_run_tm=min_run_tm,
        min_effic=min_effic,
        unit=unit,
        beam_type=beam_type,
    )
    if key:
        rows = [r for r in rows if r.key == key]
    return rows
