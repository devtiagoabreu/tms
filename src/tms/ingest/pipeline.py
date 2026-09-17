"""Pipeline de ingestão: arquivos legados de `tmsdata/` → PostgreSQL.

Lê os parsers puros de `tms.ingest` e faz upsert idempotente nas tabelas:

- `current/current.txt`  → `machines` + `machine_snapshots`
- `current/setting.txt`  → `machine_snapshots` + `shift_schedules`
- `shift/*.txt`          → `daily_raw` (+ `agg_shift` calculado via core.stopcodes)
- `stop_history/**/*.txt`→ `stop_events`

Todas as funções são idempotentes por chave natural (reamostrar o mesmo
diretório não duplica linhas) e **não** dão commit — quem chama decide.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from tms.core.formulas import effic
from tms.core.stopcodes import get_detail_stop
from tms.ingest.current_file import (
    CurrentRecord,
    SettingRecord,
    parse_current_file,
    parse_setting_file,
)
from tms.ingest.loom_file import parse_loom_file
from tms.ingest.operator_file import parse_operator_line
from tms.ingest.shift_file import ShiftRecord, parse_shift_line
from tms.ingest.stophistory_file import parse_stophistory_file
from tms.models.masters import Machine, Operator, ShiftSchedule
from tms.models.runtime import (
    AggShift,
    DailyRaw,
    MachineSnapshot,
    OperatorDaily,
    StopEvent,
)

_RAW_LEN = {"JAT": 40, "LWT": 31}

_TYPE_ALIASES = {
    "JAT700": "JAT",
    "JAT710": "JAT",
    "LW700": "LWT",
    "LWT700": "LWT",
    "LWT710": "LWT",
}


def normalize_machine_type(mac_type: Optional[str]) -> str:
    """Normaliza `JAT710`/`LW700`… para `JAT`/`LWT` (valor do domínio)."""
    return _TYPE_ALIASES.get((mac_type or "").upper(), (mac_type or "JAT").upper())


@dataclass
class IngestStats:
    """Contadores do que foi ingerido (útil p/ relatório/diagnóstico)."""

    machines: int = 0
    operators: int = 0
    snapshots: int = 0
    shift_schedules: int = 0
    daily_raw: int = 0
    operator_daily: int = 0
    stop_events: int = 0
    agg_shift: int = 0
    files: int = 0

    def __iadd__(self, other: "IngestStats") -> "IngestStats":
        for f in fields(self):
            setattr(self, f.name, getattr(self, f.name) + getattr(other, f.name))
        return self


def _day_of(shift_id: str) -> str:
    """`2025.10.01.0` → `2025.10.01`."""
    return ".".join(shift_id.split(".")[:3])


def _raw_array(values: List[int], mac_type: str) -> List[int]:
    """Normaliza o array cru (40 JAT / 31 LWT) preenchendo com zeros."""
    size = _RAW_LEN.get(mac_type.upper(), 40)
    padded = list(values[:size]) + [0] * max(0, size - len(values))
    return padded


def _joined(values: List[int]) -> str:
    return " ".join(str(v) for v in values)[:32]


def ensure_machine(
    db: Session,
    mac_name: str,
    mac_type: Optional[str] = None,
    ip_addr: Optional[str] = None,
) -> tuple[Machine, bool]:
    """Busca/cria `machines` por `mac_name`. Retorna (máquina, criada)."""
    machine = db.execute(
        select(Machine).where(Machine.mac_name == mac_name)
    ).scalar_one_or_none()
    if machine is None:
        machine = Machine(
            mac_name=mac_name,
            mac_type=normalize_machine_type(mac_type),
            ip_addr=ip_addr or None,
        )
        db.add(machine)
        db.flush()
        return machine, True
    if mac_type:
        machine.mac_type = normalize_machine_type(mac_type)
    if ip_addr:
        machine.ip_addr = ip_addr
    return machine, False


def _snapshot_payload(record: CurrentRecord) -> Dict[str, object]:
    payload: Dict[str, object] = {
        "mac_name": record.mac_name,
        "mac_type": record.mac_type,
        "ip_addr": record.ip_addr,
        "shift": record.shift,
        "get_time": record.get_time.isoformat() if record.get_time else None,
        "sys_time": record.sys_time.isoformat() if record.sys_time else None,
        "rtc_time": record.rtc_time.isoformat() if record.rtc_time else None,
        "style": record.style,
        "beam": record.beam,
        "ubeam": record.ubeam,
        "count_unit": record.count_unit,
        "s_beam": record.s_beam,
        "r_beam": record.r_beam,
        "s_ubeam": record.s_ubeam,
        "r_ubeam": record.r_ubeam,
        "cloth_len": record.cloth_len,
        "cut_len": record.cut_len,
        "doff_fcst": record.doff_fcst,
        "wout_fcst": record.wout_fcst,
        "uwout_fcst": record.uwout_fcst,
    }
    return payload


def _upsert_snapshot(db: Session, machine: Machine, record: CurrentRecord) -> bool:
    snapshot = db.execute(
        select(MachineSnapshot).where(
            MachineSnapshot.machine_id == machine.id,
            MachineSnapshot.shift_id == (record.shift or None),
            MachineSnapshot.get_time == record.get_time,
        )
    ).scalar_one_or_none()
    values = dict(
        sys_time=record.sys_time,
        rtc_time=record.rtc_time,
        style=record.style or None,
        beam=record.beam or None,
        ubeam=record.ubeam or None,
        s_beam=_joined(record.s_beam) or None,
        r_beam=_joined(record.r_beam) or None,
        cloth_len=_joined(record.cloth_len) or None,
        cut_len=_joined(record.cut_len) or None,
        doff_fcst=record.doff_fcst,
        wout_fcst=record.wout_fcst,
        uwout_fcst=record.uwout_fcst,
        raw=_snapshot_payload(record),
    )
    if snapshot is None:
        snapshot = MachineSnapshot(
            machine_id=machine.id,
            shift_id=record.shift or None,
            get_time=record.get_time,
            **values,
        )
        db.add(snapshot)
        return True
    for key, value in values.items():
        setattr(snapshot, key, value)
    return False


def ingest_current(db: Session, text: str) -> IngestStats:
    """`current/current.txt` → machines + machine_snapshots."""
    stats = IngestStats()
    for record in parse_current_file(text):
        if not record.mac_name:
            continue
        machine, created = ensure_machine(db, record.mac_name, record.mac_type, record.ip_addr)
        if created:
            stats.machines += 1
        if _upsert_snapshot(db, machine, record):
            stats.snapshots += 1
    db.flush()
    return stats


def ingest_setting(db: Session, text: str) -> IngestStats:
    """`current/setting.txt` → machine_snapshots (rtc) + shift_schedules."""
    stats = IngestStats()
    for record in parse_setting_file(text):
        if not record.mac_name:
            continue
        machine, created = ensure_machine(db, record.mac_name, record.mac_type, record.ip_addr)
        if created:
            stats.machines += 1
        rtc_record = CurrentRecord(**{f.name: getattr(record, f.name) for f in fields(CurrentRecord)})
        if _upsert_snapshot(db, machine, rtc_record):
            stats.snapshots += 1
        schedule = db.execute(
            select(ShiftSchedule).where(ShiftSchedule.code == record.mac_name)
        ).scalar_one_or_none()
        schedule_json = {
            "simple": record.simple,
            "days": {str(k): v for k, v in record.days.items()},
            "names": {str(k): v for k, v in record.names.items()},
        }
        if schedule is None:
            db.add(
                ShiftSchedule(
                    code=record.mac_name,
                    shift_mode=record.shift_mode,
                    simple=" ".join(record.simple) or None,
                    day_start_time=record.day_start_time or "6:0",
                    schedule_json=schedule_json,
                )
            )
            stats.shift_schedules += 1
        else:
            schedule.shift_mode = record.shift_mode
            schedule.simple = " ".join(record.simple) or None
            schedule.day_start_time = record.day_start_time or "6:0"
            schedule.schedule_json = schedule_json
    db.flush()
    return stats


def build_agg(record: ShiftRecord, shift_id: str) -> AggShift:
    """Calcula a linha agregada (12 categorias) de um registro bruto.

    Reaproveita `core.stopcodes.get_detail_stop` para agrupar tanto as
    contagens (`s_ct`) quanto os tempos (`s_tm`, segundos → minutos).
    """
    mac_type = record.mac_type or "JAT"
    detail_ct = get_detail_stop(mac_type, _raw_array(record.s_ct, mac_type))
    detail_tm = get_detail_stop(mac_type, _raw_array(record.s_tm, mac_type))
    run_min = record.run_tm_sec / 60.0
    stop_min = record.stop_ttm_sec / 60.0
    return AggShift(
        shift_id=shift_id,
        style=record.style or None,
        beam=record.beam or None,
        ubeam=record.ubeam or None,
        seisan_1=record.seisan[0] / 10.0 if len(record.seisan) > 0 else None,
        seisan_2=record.seisan[1] / 10.0 if len(record.seisan) > 1 else None,
        seisan_3=record.seisan[2] / 10.0 if len(record.seisan) > 2 else None,
        off_prod_1=record.off_prod[0] / 10.0 if len(record.off_prod) > 0 else None,
        off_prod_2=record.off_prod[1] / 10.0 if len(record.off_prod) > 1 else None,
        off_prod_3=record.off_prod[2] / 10.0 if len(record.off_prod) > 2 else None,
        run_tm=run_min,
        stop_ttm=stop_min,
        effic=effic(run_min, stop_min),
        stop_ct=detail_ct["stop_ct"],
        stop_tm=[v / 60.0 for v in detail_tm["stop_ct"]],
        wf1_ct=detail_ct["wf1"],
        wf1_tm=[v / 60.0 for v in detail_tm["wf1"]],
        wf2_ct=detail_ct["wf2"],
        wf2_tm=[v / 60.0 for v in detail_tm["wf2"]],
        lh_ct=detail_ct["lh"],
        lh_tm=[v / 60.0 for v in detail_tm["lh"]],
    )


def _upsert_agg(db: Session, record: ShiftRecord, shift_id: str, machine_id: int) -> None:
    agg = db.execute(
        select(AggShift).where(
            AggShift.shift_id == shift_id,
            AggShift.machine_id == machine_id,
        )
    ).scalar_one_or_none()
    built = build_agg(record, shift_id)
    if agg is None:
        built.machine_id = machine_id
        db.add(built)
        return
    for key, value in built.__dict__.items():
        if key.startswith("_sa_") or key in ("id", "machine_id", "operator_id"):
            continue
        setattr(agg, key, value)


def ingest_shift(db: Session, text: str, shift_id: Optional[str] = None) -> IngestStats:
    """`shift/<date>.<n>.txt` → daily_raw + agg_shift."""
    stats = IngestStats()
    for line in text.splitlines():
        record = parse_shift_line(line)
        if record is None or not record.mac_name:
            continue
        sid = shift_id or record.shift
        if not sid:
            continue
        day = _day_of(sid)
        machine, created = ensure_machine(db, record.mac_name, record.mac_type, record.ip_addr)
        if created:
            stats.machines += 1

        job = db.execute(
            select(DailyRaw).where(
                DailyRaw.machine_id == machine.id,
                DailyRaw.shift_id == sid,
            )
        ).scalar_one_or_none()
        seisan = {"seisan": record.seisan, "off_prod": record.off_prod}
        if job is None:
            db.add(
                DailyRaw(
                    machine_id=machine.id,
                    day=day,
                    shift_id=sid,
                    seisan=seisan,
                    run_tm=record.run_tm_sec,
                    stop_ttm=record.stop_ttm_sec,
                    s_ct=record.s_ct,
                    s_tm=record.s_tm,
                    raw_line=line.strip(),
                )
            )
            stats.daily_raw += 1
        else:
            job.day = day
            job.seisan = seisan
            job.run_tm = record.run_tm_sec
            job.stop_ttm = record.stop_ttm_sec
            job.s_ct = record.s_ct
            job.s_tm = record.s_tm
            job.raw_line = line.strip()

        _upsert_agg(db, record, sid, machine.id)
        stats.agg_shift += 1
    db.flush()
    return stats


def rebuild_agg(
    db: Session,
    *,
    day_from: Optional[str] = None,
    day_to: Optional[str] = None,
    mac_name: Optional[str] = None,
) -> IngestStats:
    """Recalcula `agg_shift` a partir de `daily_raw` (apaga/devolve o período).

    Reaproveita o `raw_line` de cada `daily_raw`, então mudanças no mapeamento de
    categorias (`core.stopcodes`) se refletem sem reingerir os arquivos.
    """
    stats = IngestStats()
    stmt = select(DailyRaw, Machine.mac_name).join(Machine, Machine.id == DailyRaw.machine_id)
    if mac_name:
        stmt = stmt.where(Machine.mac_name == mac_name)
    if day_from:
        stmt = stmt.where(DailyRaw.day >= day_from)
    if day_to:
        stmt = stmt.where(DailyRaw.day <= day_to)
    rows = list(db.execute(stmt))

    del_stmt = delete(AggShift)
    if day_from:
        del_stmt = del_stmt.where(AggShift.shift_id >= day_from)
    if day_to:
        del_stmt = del_stmt.where(AggShift.shift_id <= f"{day_to}.9")
    if mac_name:
        del_stmt = del_stmt.where(
            AggShift.machine_id.in_(select(Machine.id).where(Machine.mac_name == mac_name))
        )
    db.execute(del_stmt)

    for row, _mac in rows:
        rec = parse_shift_line(row.raw_line) if row.raw_line else None
        sid = row.shift_id or (rec.shift if rec else None)
        if rec is None or not sid:
            continue
        _upsert_agg(db, rec, sid, row.machine_id)
        stats.agg_shift += 1
    db.flush()
    return stats


def ingest_stophistory(db: Session, text: str) -> IngestStats:
    """`stop_history/<data>/<mac>.txt` → stop_events (substitui o dia)."""
    stats = IngestStats()
    parsed = parse_stophistory_file(text)
    if not parsed.mac_name:
        return stats
    machine, created = ensure_machine(db, parsed.mac_name, parsed.mac_type, parsed.ip_addr)
    if created:
        stats.machines += 1

    db.execute(
        delete(StopEvent).where(
            StopEvent.machine_id == machine.id,
            StopEvent.day == parsed.day,
        )
    )
    day_date = parsed.day_date.date() if parsed.day_date else None
    for interval in parsed.events:
        stop_start = (
            datetime.combine(day_date, interval.stop_time)
            if day_date and interval.stop_time
            else None
        )
        stop_end = (
            datetime.combine(day_date, interval.run_time)
            if day_date and interval.run_time
            else None
        )
        duration_min = None
        if stop_start and stop_end:
            duration_min = (stop_end - stop_start).total_seconds() / 60.0
        db.add(
            StopEvent(
                machine_id=machine.id,
                shift_id=None,
                day=parsed.day,
                stop_time=(
                    interval.stop_time.hour * 3600
                    + interval.stop_time.minute * 60
                    + interval.stop_time.second
                    if interval.stop_time
                    else 0
                ),
                run_time=(
                    interval.run_time.hour * 3600
                    + interval.run_time.minute * 60
                    + interval.run_time.second
                    if interval.run_time
                    else 0
                ),
                raw_code=interval.code,
                fixed=parsed.fixed,
                stop_start=stop_start,
                stop_end=stop_end,
                duration_min=duration_min,
            )
        )
        stats.stop_events += 1
    db.flush()
    return stats


SOURCES = ("current", "setting", "shift", "operator", "stophistory", "loom")


def _resolve_sources(sources: Optional[Iterable[str]]) -> set[str]:
    if sources is None:
        return set(SOURCES)
    if isinstance(sources, str):
        sources = [sources]
    resolved = set()
    for source in sources:
        for item in str(source).replace(",", " ").split():
            if item == "all":
                return set(SOURCES)
            if item not in SOURCES:
                raise ValueError(f"fonte desconhecida: {item!r} (use {SOURCES} ou 'all')")
            resolved.add(item)
    return resolved


def ensure_operator(db: Session, code: str, name: str = "") -> tuple[Operator, bool]:
    """Busca/cria `operators` por `code` (ope_num), atualizando o nome."""
    code = code or "0"
    operator = db.execute(
        select(Operator).where(Operator.code == code)
    ).scalar_one_or_none()
    if operator is None:
        operator = Operator(code=code, name=name or code)
        db.add(operator)
        db.flush()
        return operator, True
    if name and operator.name != name:
        operator.name = name
    return operator, False


def ingest_operator(db: Session, text: str) -> IngestStats:
    """`operator/<data>.txt` → operators + operator_daily."""
    stats = IngestStats()
    for line in text.splitlines():
        record = parse_operator_line(line)
        if record is None or not record.mac_name or not record.day:
            continue
        machine, created = ensure_machine(
            db, record.mac_name, record.mac_type, record.ip_addr
        )
        if created:
            stats.machines += 1
        operator, created_op = ensure_operator(db, record.ope_num, record.ope_name)
        if created_op:
            stats.operators += 1

        job = db.execute(
            select(OperatorDaily).where(
                OperatorDaily.machine_id == machine.id,
                OperatorDaily.operator_id == operator.id,
                OperatorDaily.day == record.day,
            )
        ).scalar_one_or_none()
        values = dict(
            start_time=record.start,
            seisan={"seisan": record.seisan},
            run_tm=record.run_tm_sec,
            stop_ttm=record.stop_ttm_sec,
            s_ct=record.s_ct,
            s_tm=record.s_tm,
            raw_line=line.strip(),
        )
        if job is None:
            db.add(
                OperatorDaily(
                    machine_id=machine.id,
                    operator_id=operator.id,
                    day=record.day,
                    **values,
                )
            )
            stats.operator_daily += 1
        else:
            for key, value in values.items():
                setattr(job, key, value)
    db.flush()
    return stats


def ingest_loom(db: Session, text: str) -> IngestStats:
    """`loom/<mac>.txt` → machines + machine_snapshots (secção `current`).

    A secção `stop_history` do loom é dado transitório e já é coberta por
    `stop_history/<data>/<mac>.txt`, então não é duplicada aqui.
    """
    stats = IngestStats()
    loom = parse_loom_file(text)
    if not loom.mac_name:
        return stats
    machine, created = ensure_machine(db, loom.mac_name, loom.mac_type, loom.ip_addr)
    if created:
        stats.machines += 1

    shift_id = ""
    if loom.get_time and loom.shift:
        shift_id = f"{loom.get_time:%Y.%m.%d}.{loom.shift}"
    record = CurrentRecord(
        mac_name=loom.mac_name,
        mac_type=loom.mac_type,
        ip_addr=loom.ip_addr,
        shift=shift_id,
        get_time=loom.get_time,
        sys_time=loom.sys_time,
        rtc_time=loom.rtc_time,
        style=loom.style,
        beam=loom.beam,
        ubeam=loom.ubeam,
        s_beam=loom.s_beam,
        r_beam=loom.r_beam,
        cloth_len=loom.cloth_len,
        cut_len=loom.cut_len,
        doff_fcst=loom.doff_fcst,
        wout_fcst=loom.wout_fcst,
        uwout_fcst=loom.uwout_fcst,
    )
    if _upsert_snapshot(db, machine, record):
        stats.snapshots += 1
    db.flush()
    return stats


def ingest_directory(
    db: Session,
    root: str | Path,
    *,
    sources: Optional[Iterable[str]] = None,
    commit: bool = True,
) -> IngestStats:
    """Percorre um `tmsdata/` e ingere as fontes suportadas.

    `sources` restringe a ingestão (subconjunto de `SOURCES`, ou ``"all"``).
    Com ``commit=False`` nada é persistido (útil para dry-run).
    """
    root = Path(root)
    selected = _resolve_sources(sources)
    total = IngestStats()

    current = root / "current"
    for name, source, fn in (
        ("current.txt", "current", ingest_current),
        ("setting.txt", "setting", ingest_setting),
    ):
        path = current / name
        if source in selected and path.is_file():
            total += fn(db, path.read_text(encoding="utf-8", errors="replace"))
            total.files += 1

    shift_dir = root / "shift"
    if "shift" in selected and shift_dir.is_dir():
        for path in sorted(shift_dir.glob("*.txt")):
            total += ingest_shift(
                db, path.read_text(encoding="utf-8", errors="replace"), path.stem
            )
            total.files += 1

    stop_dir = root / "stop_history"
    if "stophistory" in selected and stop_dir.is_dir():
        for path in sorted(stop_dir.glob("*/*.txt")):
            total += ingest_stophistory(db, path.read_text(encoding="utf-8", errors="replace"))
            total.files += 1

    operator_dir = root / "operator"
    if "operator" in selected and operator_dir.is_dir():
        for path in sorted(operator_dir.glob("*.txt")):
            total += ingest_operator(db, path.read_text(encoding="utf-8", errors="replace"))
            total.files += 1

    loom_dir = root / "loom"
    if "loom" in selected and loom_dir.is_dir():
        for path in sorted(loom_dir.glob("*.txt")):
            total += ingest_loom(db, path.read_text(encoding="utf-8", errors="replace"))
            total.files += 1

    if commit:
        db.commit()
    return total


def preview_directory(
    root: str | Path, *, sources: Optional[Iterable[str]] = None
) -> IngestStats:
    """Conta o que seria ingerido, sem abrir banco (dry-run puro)."""
    root = Path(root)
    selected = _resolve_sources(sources)
    stats = IngestStats()
    mac_names: set[str] = set()

    current = root / "current"
    for name, source in (("current.txt", "current"), ("setting.txt", "setting")):
        path = current / name
        if source not in selected or not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        records = parse_current_file(text) if source == "current" else parse_setting_file(text)
        stats.files += 1
        stats.snapshots += len(records)
        if source == "setting":
            stats.shift_schedules += len(records)
        mac_names.update(r.mac_name for r in records if r.mac_name)

    shift_dir = root / "shift"
    if "shift" in selected and shift_dir.is_dir():
        for path in sorted(shift_dir.glob("*.txt")):
            for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
                record = parse_shift_line(line)
                if record is None or not record.mac_name:
                    continue
                stats.daily_raw += 1
                stats.agg_shift += 1
                mac_names.add(record.mac_name)
            stats.files += 1

    stop_dir = root / "stop_history"
    if "stophistory" in selected and stop_dir.is_dir():
        for path in sorted(stop_dir.glob("*/*.txt")):
            parsed = parse_stophistory_file(
                path.read_text(encoding="utf-8", errors="replace")
            )
            if not parsed.mac_name:
                continue  # ex.: index.txt
            stats.stop_events += len(parsed.events)
            mac_names.add(parsed.mac_name)
            stats.files += 1

    operator_dir = root / "operator"
    if "operator" in selected and operator_dir.is_dir():
        for path in sorted(operator_dir.glob("*.txt")):
            for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
                record = parse_operator_line(line)
                if record is None or not record.mac_name or not record.day:
                    continue
                stats.operator_daily += 1
                mac_names.add(record.mac_name)
            stats.files += 1

    loom_dir = root / "loom"
    if "loom" in selected and loom_dir.is_dir():
        for path in sorted(loom_dir.glob("*.txt")):
            loom = parse_loom_file(path.read_text(encoding="utf-8", errors="replace"))
            if not loom.mac_name:
                continue
            if loom.get_time is not None:
                stats.snapshots += 1
            mac_names.add(loom.mac_name)
            stats.files += 1

    stats.machines = len(mac_names)
    return stats
