"""Agregação de período (turno/dia/semana/mês) a partir dos registros.

Espelha `common/TMSDATAfinal.pm`:

- agrupa por ``(mac_name, mac_type, style, beam, ubeam)`` no modo tear/estilo
  e por ``(período, operador)`` no modo operador;
- soma ``seisan``/``off_prod`` (décimos), ``run_tm``/``stop_ttm`` (segundos) e
  os arrays crus de parada, **sem** tirar médias;
- recomputa EFFIC/RPM a partir das somas (nunca média de taxas);
- filtra cada registro por ``run_tm >= min_run_tm`` (minutos) e
  ``effic >= min_effic`` **antes** de agregar;
- semana ancorada no início configurável (0 = domingo, como o legado), não ISO.

Período ``shift`` usa o `shift_id` completo (``YYYY.MM.DD.n``) como chave.
O modo operador agrega `operator_daily` por nome do operador (sem
granularidade de turno).
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
    shiftreport_total2,
)
from tms.core.stopcodes import get_detail_stop
from tms.ingest.shift_file import parse_shift_line
from tms.models.masters import Machine, Operator
from tms.models.runtime import AggShift, DailyRaw, OperatorDaily

# 0 = domingo (default do selitem legado). 1 = segunda, ...
WEEK_START = 0

PERIODS = ("shift", "day", "week", "month")

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
    shift_id: Optional[str] = None  # YYYY.MM.DD.n (usado no período "shift")

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
    operator: Optional[str] = None
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
    loom_count: int = 0  # nº de teares distintos (stylereport)

    def production(self, unit: int = UNIT_PICK) -> float:
        return production(self.seisan, self.off_prod, unit)

    def total_ct(self, beam_type: int = 1) -> int:
        return shiftreport_total(self.stop_ct, beam_type)

    def total2_ct(self, beam_type: int = 1) -> int:
        return shiftreport_total2(self.stop_ct, beam_type)


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
    if period == "shift":
        return day
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
        if period == "shift":
            day = rec.shift_id or rec.day
        else:
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
        shift_id=row.shift_id,
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


@dataclass(frozen=True)
class AggRecord:
    """Linha de `agg_shift` (12 categorias) para re-agregação por período.

    ``seisan``/``off_prod`` já vêm divididos por 10; ``run_tm``/``stop_ttm`` em
    minutos. Diferente de `RawRecord`, os arrays de parada já estão no
    mapeamento de 12 categorias.
    """

    mac_name: str
    mac_type: str
    style: Optional[str]
    beam: Optional[str]
    ubeam: Optional[str]
    seisan: tuple[float, ...] = ()  # /10
    off_prod: tuple[float, ...] = ()  # /10
    run_tm: float = 0.0  # minutos
    stop_ttm: float = 0.0  # minutos
    stop_ct: tuple[int, ...] = ()  # 12
    stop_tm: tuple[float, ...] = ()  # 12 (min)
    wf1_ct: tuple[int, ...] = ()
    wf1_tm: tuple[float, ...] = ()
    wf2_ct: tuple[int, ...] = ()
    wf2_tm: tuple[float, ...] = ()
    lh_ct: tuple[int, ...] = ()
    lh_tm: tuple[float, ...] = ()
    day: Optional[str] = None  # YYYY.MM.DD (de shift_id)
    shift_id: Optional[str] = None  # YYYY.MM.DD.n (período "shift")
    operator_name: Optional[str] = None  # modo operador

    def effic(self) -> float:
        return effic(self.run_tm, self.stop_ttm)


def _agg_record(row: AggShift, mac_name: str, mac_type: str) -> AggRecord:
    shift_id = row.shift_id or ""
    return AggRecord(
        mac_name=mac_name,
        mac_type=mac_type,
        style=row.style,
        beam=row.beam,
        ubeam=row.ubeam,
        seisan=(row.seisan_1 or 0.0, row.seisan_2 or 0.0, row.seisan_3 or 0.0),
        off_prod=(row.off_prod_1 or 0.0, row.off_prod_2 or 0.0, row.off_prod_3 or 0.0),
        run_tm=row.run_tm or 0.0,
        stop_ttm=row.stop_ttm or 0.0,
        stop_ct=tuple(row.stop_ct or []),
        stop_tm=tuple(row.stop_tm or []),
        wf1_ct=tuple(row.wf1_ct or []),
        wf1_tm=tuple(row.wf1_tm or []),
        wf2_ct=tuple(row.wf2_ct or []),
        wf2_tm=tuple(row.wf2_tm or []),
        lh_ct=tuple(row.lh_ct or []),
        lh_tm=tuple(row.lh_tm or []),
        day=shift_id[:10] or None,
        shift_id=shift_id or None,
    )


def load_agg_records(
    db: Session,
    *,
    day_from: Optional[str] = None,
    day_to: Optional[str] = None,
    mac_name: Optional[str] = None,
) -> list[AggRecord]:
    """Carrega `agg_shift` (join `machines`) como `AggRecord`s.

    `shift_id` tem o formato ``YYYY.MM.DD.n``; o filtro por data usa o prefixo.
    """
    stmt = select(AggShift, Machine.mac_name, Machine.mac_type).join(
        Machine, Machine.id == AggShift.machine_id
    )
    if mac_name:
        stmt = stmt.where(Machine.mac_name == mac_name)
    if day_from:
        stmt = stmt.where(AggShift.shift_id >= day_from)
    if day_to:
        stmt = stmt.where(AggShift.shift_id <= f"{day_to}.9")
    stmt = stmt.order_by(AggShift.shift_id, Machine.mac_name)
    return [_agg_record(row, name, mac_type) for row, name, mac_type in db.execute(stmt)]


def _operator_record(
    row: OperatorDaily, mac_name: str, mac_type: str, operator_name: str
) -> AggRecord:
    """`operator_daily` → `AggRecord` (12 categorias via `get_detail_stop`)."""
    seisan = (row.seisan or {}).get("seisan", [])
    style = beam = ubeam = None
    if row.raw_line:
        parsed = parse_shift_line(row.raw_line)
        if parsed is not None:
            style, beam, ubeam = parsed.style, parsed.beam, parsed.ubeam
    detail_ct = get_detail_stop(mac_type, _padded(row.s_ct, mac_type))
    detail_tm = get_detail_stop(mac_type, _padded(row.s_tm, mac_type))
    return AggRecord(
        mac_name=mac_name,
        mac_type=mac_type,
        style=style or None,
        beam=beam or None,
        ubeam=ubeam or None,
        seisan=tuple(round(v / 10.0, 1) for v in seisan[:3]),
        off_prod=(0.0, 0.0, 0.0),
        run_tm=(row.run_tm or 0) / 60.0,
        stop_ttm=(row.stop_ttm or 0) / 60.0,
        stop_ct=tuple(detail_ct["stop_ct"]),
        stop_tm=tuple(round(v / 60.0, 3) for v in detail_tm["stop_ct"]),
        wf1_ct=tuple(detail_ct["wf1"]),
        wf1_tm=tuple(round(v / 60.0, 3) for v in detail_tm["wf1"]),
        wf2_ct=tuple(detail_ct["wf2"]),
        wf2_tm=tuple(round(v / 60.0, 3) for v in detail_tm["wf2"]),
        lh_ct=tuple(detail_ct["lh"]),
        lh_tm=tuple(round(v / 60.0, 3) for v in detail_tm["lh"]),
        day=row.day,
        operator_name=operator_name,
    )


def load_operator_records(
    db: Session,
    *,
    day_from: Optional[str] = None,
    day_to: Optional[str] = None,
    mac_name: Optional[str] = None,
    operator_name: Optional[str] = None,
) -> list[AggRecord]:
    """Carrega `operator_daily` (join `machines`/`operators`) como `AggRecord`s
    com `operator_name` para agregação no modo operador.

    Sem granularidade de turno (uma linha por tear × operador × dia).
    """
    stmt = (
        select(OperatorDaily, Machine.mac_name, Machine.mac_type, Operator.name)
        .join(Machine, Machine.id == OperatorDaily.machine_id)
        .join(Operator, Operator.id == OperatorDaily.operator_id)
    )
    if mac_name:
        stmt = stmt.where(Machine.mac_name == mac_name)
    if operator_name:
        stmt = stmt.where(Operator.name == operator_name)
    if day_from:
        stmt = stmt.where(OperatorDaily.day >= day_from)
    if day_to:
        stmt = stmt.where(OperatorDaily.day <= day_to)
    stmt = stmt.order_by(OperatorDaily.day, Operator.name, Machine.mac_name)
    return [
        _operator_record(row, name, mac_type, ope_name)
        for row, name, mac_type, ope_name in db.execute(stmt)
    ]


@dataclass
class _AggAcc:
    mac_name: str
    mac_type: str
    style: Optional[str]
    beam: Optional[str]
    ubeam: Optional[str]
    operator_name: str = ""
    seisan: list[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    off_prod: list[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    run_tm: float = 0.0
    stop_ttm: float = 0.0
    stop_ct: list[int] = field(default_factory=list)
    stop_tm: list[float] = field(default_factory=list)
    wf1_ct: list[int] = field(default_factory=list)
    wf1_tm: list[float] = field(default_factory=list)
    wf2_ct: list[int] = field(default_factory=list)
    wf2_tm: list[float] = field(default_factory=list)
    lh_ct: list[int] = field(default_factory=list)
    lh_tm: list[float] = field(default_factory=list)
    machines: set[str] = field(default_factory=set)


def _sum_into(acc: list, values: Iterable, size: int, *, as_float: bool = False) -> list:
    if not acc:
        acc.extend([0.0 if as_float else 0] * size)
    for i, v in enumerate(list(values)[:size]):
        acc[i] += v
    return acc


def aggregate_agg_records(
    records: Iterable[AggRecord],
    period: str,
    *,
    week_start: int = WEEK_START,
    min_run_tm: float = 0.0,
    min_effic: float = 0.0,
    unit: int = UNIT_PICK,
    beam_type: int = 1,
    group_by: str = "loom",
) -> list[PeriodRow]:
    """Agrega `agg_shift` por período (soma as 12 categorias, sem médias).

    ``group_by="loom"`` agrupa por ``(mac_name, mac_type, style, beam, ubeam)``;
    ``group_by="operator"`` agrupa por ``(período, operator_name)``;
    ``group_by="style"`` agrupa por ``(período, style)`` (stylereport) e guarda
    em `loom_count` o nº de teares distintos.
    """
    if group_by not in ("loom", "operator", "style"):
        raise ValueError(f"agrupamento inválido: {group_by}")
    accs: dict[tuple, _AggAcc] = {}
    for rec in records:
        if rec.run_tm < min_run_tm:
            continue
        if min_effic and rec.effic() < min_effic:
            continue
        if period == "shift":
            day = rec.shift_id or rec.day
        else:
            day = rec.day
        if day is None:
            raise ValueError("registro sem data (shift_id)")
        base = period_key(period, day, week_start)
        if group_by == "operator":
            key = (base, rec.operator_name or "")
        elif group_by == "style":
            key = (base, rec.style or "")
        else:
            key = (base, rec.mac_name, rec.mac_type, rec.style, rec.beam, rec.ubeam)
        acc = accs.get(key)
        if acc is None:
            acc = _AggAcc(
                rec.mac_name, rec.mac_type, rec.style, rec.beam, rec.ubeam,
                operator_name=rec.operator_name or "",
            )
            accs[key] = acc
        acc.machines.add(rec.mac_name)
        for i, v in enumerate(rec.seisan[:3]):
            acc.seisan[i] += v
        for i, v in enumerate(rec.off_prod[:3]):
            acc.off_prod[i] += v
        acc.run_tm += rec.run_tm
        acc.stop_ttm += rec.stop_ttm
        _sum_into(acc.stop_ct, rec.stop_ct, 12)
        _sum_into(acc.stop_tm, rec.stop_tm, 12, as_float=True)
        _sum_into(acc.wf1_ct, rec.wf1_ct, len(rec.wf1_ct))
        _sum_into(acc.wf1_tm, rec.wf1_tm, len(rec.wf1_tm), as_float=True)
        _sum_into(acc.wf2_ct, rec.wf2_ct, len(rec.wf2_ct))
        _sum_into(acc.wf2_tm, rec.wf2_tm, len(rec.wf2_tm), as_float=True)
        _sum_into(acc.lh_ct, rec.lh_ct, len(rec.lh_ct))
        _sum_into(acc.lh_tm, rec.lh_tm, len(rec.lh_tm), as_float=True)

    rows: list[PeriodRow] = []
    for key, acc in sorted(accs.items(), key=lambda kv: (kv[0][0], kv[0][1])):
        run_min = round(acc.run_tm, 3)
        stop_min = round(acc.stop_ttm, 3)
        seisan_final = [round(v, 1) for v in acc.seisan]
        off_final = [round(v, 1) for v in acc.off_prod]
        rows.append(
            PeriodRow(
                period=period,
                key=key[0],
                mac_name=acc.mac_name,
                mac_type=acc.mac_type,
                style=acc.style,
                beam=acc.beam,
                ubeam=acc.ubeam,
                operator=acc.operator_name or None,
                seisan=seisan_final,
                off_prod=off_final,
                run_tm=run_min,
                stop_ttm=stop_min,
                effic=effic(acc.run_tm, acc.stop_ttm),
                rpm=rpm_from_agg(seisan_final[0] if seisan_final else 0.0, run_min),
                stop_ct=list(acc.stop_ct),
                stop_tm=[round(v, 3) for v in acc.stop_tm],
                wf1_ct=list(acc.wf1_ct),
                wf1_tm=[round(v, 3) for v in acc.wf1_tm],
                wf2_ct=list(acc.wf2_ct),
                wf2_tm=[round(v, 3) for v in acc.wf2_tm],
                lh_ct=list(acc.lh_ct),
                lh_tm=[round(v, 3) for v in acc.lh_tm],
                loom_count=len(acc.machines),
            )
        )
    return rows


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
    source: str = "agg",
    mode: str = "shift",
) -> list[PeriodRow]:
    """Agrega por período (filtra por `key`/data/tear).

    ``source="agg"`` (default) lê `agg_shift`, retido por 12 meses; ``"raw"``
    lê `daily_raw` (bruto). ``mode="operator"`` agrega `operator_daily` por
    operador (sem granularidade de turno); ``mode="style"`` agrega `agg_shift`
    por estilo (stylereport); ``mode="shift"`` é tear/estilo.
    """
    if period not in PERIODS:
        raise ValueError(f"período inválido: {period}")
    if mode == "operator" and period == "shift":
        raise ValueError("modo operador não tem granularidade de turno")
    if mode == "operator":
        rows = aggregate_agg_records(
            load_operator_records(db, day_from=day_from, day_to=day_to, mac_name=mac_name),
            period,
            week_start=week_start,
            min_run_tm=min_run_tm,
            min_effic=min_effic,
            unit=unit,
            beam_type=beam_type,
            group_by="operator",
        )
    elif mode == "style":
        if source != "agg":
            raise ValueError("modo estilo usa agg_shift (source='agg')")
        rows = aggregate_agg_records(
            load_agg_records(db, day_from=day_from, day_to=day_to, mac_name=mac_name),
            period,
            week_start=week_start,
            min_run_tm=min_run_tm,
            min_effic=min_effic,
            unit=unit,
            beam_type=beam_type,
            group_by="style",
        )
    elif source == "agg":
        rows = aggregate_agg_records(
            load_agg_records(db, day_from=day_from, day_to=day_to, mac_name=mac_name),
            period,
            week_start=week_start,
            min_run_tm=min_run_tm,
            min_effic=min_effic,
            unit=unit,
            beam_type=beam_type,
            group_by="loom",
        )
    elif source == "raw":
        rows = aggregate_records(
            load_records(db, day_from=day_from, day_to=day_to, mac_name=mac_name),
            period,
            week_start=week_start,
            min_run_tm=min_run_tm,
            min_effic=min_effic,
            unit=unit,
            beam_type=beam_type,
        )
    else:
        raise ValueError(f"fonte inválida: {source}")
    if key:
        rows = [r for r in rows if r.key == key]
    return rows


def machine_aris(db: Session) -> tuple[bool, bool]:
    """Tipos de tear presentes em `machines`: ``(existe JAT?, existe LWT?)``.

    O legado decide entre JAT/LWT misto ou único pelo ``jat_ari``/``lwt_ari``.
    """
    present = set()
    for (mac_type,) in db.execute(
        select(Machine.mac_type).where(Machine.mac_type.is_not(None))
    ):
        present.add(mac_type.upper())
    return "JAT" in present, "LWT" in present
