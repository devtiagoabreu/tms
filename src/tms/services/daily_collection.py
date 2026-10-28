"""Servico de coleta diaria dos teares.

Regras de negocio
=================

* A coleta roda **uma vez por dia** e sempre se refere ao **dia anterior**.
  A unicidade e garantida pela constraint ``uq_daily_collection_run_date`` na
  coluna ``daily_collection_runs.collection_date``: uma segunda tentativa para
  a mesma data reutiliza o registro existente em vez de criar outro.
* Cada tear tem um :class:`DailyCollectionItem` com o resultado da coleta.
* Teares desligados, fora da rede ou com erro de comunicacao entram na
  **fila de retentativa** (``in_retry_queue``) e sao reprocessados depois, sem
  refazer a coleta dos teares que ja tiveram sucesso.
* O dashboard lista explicitamente os teares que faltaram.

Fontes de dados (em ordem de prioridade)
========================================

1. ``agg_shift`` do dia anterior — dados agregados do legado (12 categorias).
2. ``daily_raw`` do dia anterior — registro bruto do legado.
3. Historico de ``live_status`` do dia anterior — medias de RPM/eficiencia.
4. Leitura ao vivo do tear no momento da coleta.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from tms.collector import fetch_live
from tms.core.formulas import effic
from tms.core.live import BIT_PRECEDENCE, live_to_monitor_state
from tms.core.stopcodes import get_detail_stop
from tms.models.daily import DailyCollectionItem, DailyCollectionRun, DailyLoomData
from tms.models.masters import Machine
from tms.models.runtime import AggShift, DailyRaw, LiveStatusRecord

log = logging.getLogger(__name__)

# Categorias de parada (indices no array de 12 do legado).
TRAMA_INDEX = 5            # WEFT_MISS  -> trama
URDUME_INDEXES = (0, 1)    # WARP_TOP_MISS + WARP_MISS -> urdume

# Estado (bits do tear) -> indice da categoria de parada.
STATE_TO_CATEGORY = {
    "Warp_top": 0,
    "Warp": 1,
    "False_selvage": 2,
    "Leno_L": 3,
    "Leno_R": 4,
    "Weft": 5,
    "Cloth_doffing": 7,
    "Manual": 8,
    "Power_off": 9,
    "Machine_failure": 10,
    "Cloth_mending": 10,
    "CatchCode_rear": 11,
    "CatchCode_front": 11,
}

# Duracao maxima atribuida a uma unica amostra (evita distorcer lacunas).
MAX_SAMPLE_MIN = 5.0

# Intervalo minimo entre tentativas automaticas da fila de retentativa.
RETRY_INTERVAL = timedelta(minutes=15)

# Hora a partir da qual a coleta automatica do dia anterior pode rodar.
COLLECTION_HOUR = 1


def get_yesterday() -> date:
    return date.today() - timedelta(days=1)


def previous_day_window(day: date) -> tuple[datetime, datetime]:
    """Janela [day 00:00, day+1 00:00)."""
    return datetime.combine(day, time.min), datetime.combine(day + timedelta(days=1), time.min)


# ---------------------------------------------------------------------------
# Execucao da coleta
# ---------------------------------------------------------------------------


def ensure_collection_run(db: Session, collection_date: date) -> tuple[DailyCollectionRun, bool]:
    """Garante uma execucao unica por dia (constraint de unicidade)."""
    run = db.execute(
        select(DailyCollectionRun).where(DailyCollectionRun.collection_date == collection_date)
    ).scalar_one_or_none()
    if run:
        return run, False
    run = DailyCollectionRun(collection_date=collection_date, status="pending")
    db.add(run)
    db.flush()
    return run, True


def _classify_error(live) -> Optional[str]:
    """Motivo para mandar o tear para a fila de retentativa (ou None)."""
    if live.error is not None:
        return f"Falha de comunicacao: {live.status} (erro={live.error})"
    state = live_to_monitor_state(live)
    if state in ("offline", "no_data"):
        return f"Tear indisponivel: {live.status} (estado={state})"
    return None


def _stop_breakdown(stop_ct, stop_tm) -> dict:
    """Agrupa as 12 categorias em trama / urdume / outros."""
    result = {
        "total_stop_ct": None,
        "total_stop_tm_min": None,
        "trama_stops": None,
        "trama_stops_min": None,
        "urdume_stops": None,
        "urdume_stops_min": None,
        "outros_stops": None,
        "outros_stops_min": None,
    }
    if not stop_ct:
        return result

    times = stop_tm or []
    total_ct = 0
    total_tm = 0.0
    trama_ct = trama_tm = 0
    urdume_ct = urdume_tm = 0
    outros_ct = 0
    outros_tm = 0.0

    for i, raw_ct in enumerate(stop_ct):
        ct = int(raw_ct or 0)
        tm = float(times[i] or 0) if i < len(times) else 0.0
        total_ct += ct
        total_tm += tm
        if i == TRAMA_INDEX:
            trama_ct += ct
            trama_tm += tm
        elif i in URDUME_INDEXES:
            urdume_ct += ct
            urdume_tm += tm
        else:
            outros_ct += ct
            outros_tm += tm

    result.update(
        total_stop_ct=total_ct,
        total_stop_tm_min=round(total_tm, 3),
        trama_stops=trama_ct,
        trama_stops_min=round(trama_tm, 3),
        urdume_stops=urdume_ct,
        urdume_stops_min=round(urdume_tm, 3),
        outros_stops=outros_ct,
        outros_stops_min=round(outros_tm, 3),
    )
    return result


def _sum_seisan(*values) -> Optional[float]:
    parts = [v for v in values if v is not None]
    if not parts:
        return None
    return round(sum(float(v) for v in parts), 3)


def _metrics_from_agg(agg: AggShift) -> dict:
    return {
        "source": "agg_shift",
        "shift_id": agg.shift_id,
        "style": agg.style,
        "beam": agg.beam,
        "production": _sum_seisan(agg.seisan_1, agg.seisan_2, agg.seisan_3),
        "efficiency": agg.effic,
        "run_time_min": agg.run_tm,
        "stop_time_min": agg.stop_ttm,
        **_stop_breakdown(agg.stop_ct, agg.stop_tm),
    }


def _metrics_from_raw(raw: DailyRaw, machine: Machine) -> dict:
    mac_type = machine.mac_type or "JAT"
    detail_ct = get_detail_stop(mac_type, list(raw.s_ct or []))
    detail_tm = get_detail_stop(mac_type, list(raw.s_tm or []))
    stop_tm_min = [v / 60.0 for v in detail_tm["stop_ct"]]
    run_min = (raw.run_tm or 0) / 60.0 if raw.run_tm is not None else None
    stop_min = (raw.stop_ttm or 0) / 60.0 if raw.stop_ttm is not None else None
    seisan = raw.seisan or {}
    production = None
    if isinstance(seisan, dict) and seisan:
        vals = [v for k, v in sorted(seisan.items()) if isinstance(v, (int, float))]
        if vals:
            production = round(sum(vals) / 10.0, 3)
    return {
        "source": "daily_raw",
        "shift_id": raw.shift_id,
        "style": None,
        "beam": None,
        "production": production,
        "efficiency": effic(run_min or 0.0, stop_min or 0.0) if run_min is not None else None,
        "run_time_min": round(run_min, 3) if run_min is not None else None,
        "stop_time_min": round(stop_min, 3) if stop_min is not None else None,
        **_stop_breakdown(detail_ct["stop_ct"], stop_tm_min),
    }


def _active_cause(bits: dict) -> Optional[str]:
    """Causa ativa segundo a precedencia do legado (ultima que casar vence)."""
    cause = None
    for bit, name in BIT_PRECEDENCE:
        if bits.get(bit):
            cause = name
    return cause


def _history_stop_breakdown(rows) -> Optional[dict]:
    """Deduz contagem/minutos por causa a partir das amostras de ``live_status``."""
    counts: dict[int, int] = {}
    minutes: dict[int, float] = {}

    prev_time = None
    prev_cause: Optional[str] = None
    for record in rows:
        if record.error is not None:
            continue
        cause = None if record.state == "run" else _active_cause(record.bits or {})

        if prev_cause is not None and prev_time is not None:
            delta = (record.collected_at - prev_time).total_seconds() / 60.0
            if 0 <= delta <= MAX_SAMPLE_MIN:
                minutes[STATE_TO_CATEGORY.get(prev_cause, 10)] = (
                    minutes.get(STATE_TO_CATEGORY.get(prev_cause, 10), 0.0) + delta
                )

        if cause is not None and cause != prev_cause:
            index = STATE_TO_CATEGORY.get(cause, 10)
            counts[index] = counts.get(index, 0) + 1

        prev_time, prev_cause = record.collected_at, cause

    if not counts and not minutes:
        return None

    stop_ct = [counts.get(i, 0) for i in range(12)]
    stop_tm = [round(minutes.get(i, 0.0), 3) for i in range(12)]
    return _stop_breakdown(stop_ct, stop_tm)


def _metrics_from_history(db: Session, machine: Machine, day: date) -> Optional[dict]:
    """Agrega o historico de ``live_status`` do dia anterior."""
    start, end = previous_day_window(day)
    rows = db.execute(
        select(LiveStatusRecord)
        .where(LiveStatusRecord.machine_id == machine.id)
        .where(LiveStatusRecord.collected_at >= start)
        .where(LiveStatusRecord.collected_at < end)
        .where(LiveStatusRecord.error.is_(None))
        .order_by(LiveStatusRecord.collected_at)
    ).scalars().all()
    if not rows:
        return None

    efficiencies = [r.efficiency for r in rows if r.efficiency is not None]
    rpms = [r.rpm for r in rows if r.rpm is not None]
    run_times = [r.data.get("run_time") for r in rows if isinstance(r.data, dict) and r.data.get("run_time") is not None]
    stop_times = [r.data.get("stop_time") for r in rows if isinstance(r.data, dict) and r.data.get("stop_time") is not None]
    shift_stops = [r.data.get("stop_shift") for r in rows if isinstance(r.data, dict) and r.data.get("stop_shift") is not None]

    style = None
    for r in reversed(rows):
        if isinstance(r.setup, dict) and r.setup.get("style"):
            style = str(r.setup["style"]).strip().strip('"')
            break

    breakdown = _history_stop_breakdown(rows)
    result = {
        "source": "history",
        "shift_id": None,
        "style": style,
        "beam": None,
        "production": None,
        "efficiency": round(sum(efficiencies) / len(efficiencies), 3) if efficiencies else None,
        "rpm": round(sum(rpms) / len(rpms), 3) if rpms else None,
        "run_time_min": round(max(run_times), 3) if run_times else None,
        "stop_time_min": round(max(stop_times), 3) if stop_times else None,
        "total_stop_ct": int(max(shift_stops)) if shift_stops else None,
    }
    if breakdown:
        # O contador do proprio tear e a referencia de total; o detalhamento por
        # causa vem das amostras coletadas ao longo do dia.
        if shift_stops:
            breakdown["total_stop_ct"] = int(max(shift_stops))
        result.update(breakdown)
    return result


def _metrics_from_live(live) -> dict:
    get = live.value if hasattr(live, "value") else (lambda _k: None)
    rpm = get("rpm")
    return {
        "source": "live",
        "shift_id": None,
        "style": live.style if hasattr(live, "style") else None,
        "beam": None,
        "production": None,
        "efficiency": live.effic_shift if hasattr(live, "effic_shift") else None,
        "rpm": float(rpm) if rpm is not None else None,
        "run_time_min": get("run_time"),
        "stop_time_min": get("stop_time"),
        "total_stop_ct": int(get("stop_shift") or 0) if get("stop_shift") is not None else None,
    }


def _resolve_metrics(db: Session, machine: Machine, day: date, live) -> dict:
    """Combina as fontes disponiveis, priorizando o dado agregado do legado."""
    day_key = day.strftime("%Y.%m.%d")

    agg = db.execute(
        select(AggShift)
        .where(AggShift.machine_id == machine.id)
        .where(AggShift.shift_id.like(f"{day_key}.%"))
        .order_by(AggShift.shift_id.desc())
    ).scalars().first()
    if agg is not None:
        metrics = _metrics_from_agg(agg)
    else:
        raw = db.execute(
            select(DailyRaw)
            .where(DailyRaw.machine_id == machine.id)
            .where(DailyRaw.day == day_key)
            .order_by(DailyRaw.shift_id.desc())
        ).scalars().first()
        if raw is not None:
            metrics = _metrics_from_raw(raw, machine)
        else:
            metrics = _metrics_from_history(db, machine, day) or {"source": "live"}

    live_metrics = _metrics_from_live(live)
    # Completa lacunas com a leitura ao vivo (sempre disponivel no sucesso).
    for key, value in live_metrics.items():
        if key == "source":
            continue
        if metrics.get(key) is None:
            metrics[key] = value
    return metrics


def _upsert_loom_data(
    db: Session, day: date, machine: Machine, metrics: dict, live
) -> DailyLoomData:
    """Cria/atualiza a linha do dashboard (idempotente por data+maquina)."""
    row = db.execute(
        select(DailyLoomData).where(
            DailyLoomData.collection_date == day,
            DailyLoomData.machine_id == machine.id,
        )
    ).scalar_one_or_none()
    if row is None:
        row = DailyLoomData(
            collection_date=day,
            machine_id=machine.id,
            mac_name=machine.mac_name,
        )
        db.add(row)

    for field in (
        "source",
        "shift_id",
        "style",
        "beam",
        "production",
        "efficiency",
        "rpm",
        "run_time_min",
        "stop_time_min",
        "total_stop_ct",
        "total_stop_tm_min",
        "trama_stops",
        "trama_stops_min",
        "urdume_stops",
        "urdume_stops_min",
        "outros_stops",
        "outros_stops_min",
    ):
        if field in metrics:
            setattr(row, field, metrics[field])

    row.mac_name = machine.mac_name
    row.collected_at = datetime.utcnow()
    row.raw_data = {
        "live_status": live.status,
        "live_error": live.error,
        "live_state": live_to_monitor_state(live),
        "mac_type": live.mac_type,
        "data": live.data,
        "setup": live.setup,
        "source": metrics.get("source"),
    }
    return row


def _collect_one(
    db: Session,
    item: DailyCollectionItem,
    day: date,
    prefetched: Optional[tuple] = None,
) -> str:
    """Coleta um tear. Retorna ``"success"`` ou ``"retry"``."""
    machine = db.get(Machine, item.machine_id)
    if machine is None:
        item.status = "failed"
        item.error_reason = "Tear nao encontrado no cadastro"
        return "retry"
    if not machine.ip_addr:
        item.status = "failed"
        item.error_reason = "IP nao configurado"
        return "retry"

    item.attempts = (item.attempts or 0) + 1
    item.last_retry_at = datetime.utcnow()

    if prefetched is not None:
        live, exc = prefetched
        if exc is not None:
            item.status = "failed"
            item.error_reason = f"Erro inesperado: {exc}"
            return "retry"
    else:
        try:
            live = fetch_live(machine.ip_addr, timeout=10.0)
        except Exception as exc:  # pragma: no cover - fetch_live nao levanta
            item.status = "failed"
            item.error_reason = f"Erro inesperado: {exc}"
            return "retry"

    reason = _classify_error(live)
    if reason:
        item.status = "failed"
        item.error_reason = reason
        return "retry"

    metrics = _resolve_metrics(db, machine, day, live)
    _upsert_loom_data(db, day, machine, metrics, live)

    item.status = "success"
    item.error_reason = None
    item.collected_at = datetime.utcnow()
    item.data_json = {
        "source": metrics.get("source"),
        "rpm": metrics.get("rpm"),
        "efficiency": metrics.get("efficiency"),
        "live_status": live.status,
    }
    return "success"


def _refresh_counters(db: Session, run: DailyCollectionRun) -> None:
    items = db.execute(
        select(DailyCollectionItem).where(DailyCollectionItem.run_id == run.id)
    ).scalars().all()
    run.total_machines = len(items)
    run.success_count = sum(1 for i in items if i.status == "success")
    run.failed_count = sum(1 for i in items if i.status != "success")
    run.retry_count = sum(1 for i in items if i.in_retry_queue)
    run.finished_at = datetime.utcnow()

    if run.total_machines == 0:
        run.status = "completed"
    elif run.failed_count == 0:
        run.status = "completed"
    elif run.success_count == 0:
        run.status = "failed"
    else:
        run.status = "partial"


def _ensure_items(db: Session, run: DailyCollectionRun) -> dict[int, DailyCollectionItem]:
    machines = db.execute(select(Machine).where(Machine.active.is_(True))).scalars().all()
    existing = {
        item.machine_id: item
        for item in db.execute(
            select(DailyCollectionItem).where(DailyCollectionItem.run_id == run.id)
        ).scalars().all()
    }
    for machine in machines:
        if machine.id not in existing:
            item = DailyCollectionItem(
                run_id=run.id,
                machine_id=machine.id,
                mac_name=machine.mac_name,
                mac_type=machine.mac_type,
                ip_addr=machine.ip_addr,
                status="pending",
                in_retry_queue=True,
            )
            db.add(item)
            existing[machine.id] = item
    db.flush()
    return existing


def _fetch_many(db: Session, items: list[DailyCollectionItem]) -> dict[int, tuple]:
    """Le os teares em paralelo (rede) para nao somar timeouts em serie."""
    from concurrent.futures import ThreadPoolExecutor

    machines = {
        m.id: m
        for m in db.execute(
            select(Machine).where(Machine.id.in_([i.machine_id for i in items]))
        ).scalars()
    }

    def work(item: DailyCollectionItem):
        machine = machines.get(item.machine_id)
        if machine is None:
            return item.machine_id, (None, None)
        if not machine.ip_addr:
            return item.machine_id, (None, None)
        try:
            return item.machine_id, (fetch_live(machine.ip_addr, timeout=10.0), None)
        except Exception as exc:  # pragma: no cover
            return item.machine_id, (None, exc)

    with ThreadPoolExecutor(max_workers=8) as pool:
        return dict(pool.map(work, items))


def collect_daily_data(
    db: Session,
    collection_date: Optional[date] = None,
    force: bool = False,
    retry_only: bool = False,
) -> DailyCollectionRun:
    """Executa a coleta do dia anterior (ou reprocessa a fila de retentativa)."""
    day = collection_date or get_yesterday()
    run, created = ensure_collection_run(db, day)

    if not created and not force:
        if run.status == "running":
            log.info("Coleta de %s ja em andamento; ignorando", day)
            return run
        if not retry_only and run.status == "completed":
            log.info("Coleta de %s ja concluida; nada a fazer", day)
            return run

    run.status = "running"
    run.started_at = run.started_at or datetime.utcnow()
    db.flush()

    items = _ensure_items(db, run)

    if retry_only:
        targets = [i for i in items.values() if i.in_retry_queue]
    elif force or created:
        targets = list(items.values())
    else:
        targets = [i for i in items.values() if i.status != "success" or i.in_retry_queue]

    prefetched = _fetch_many(db, targets) if targets else {}
    for item in targets:
        result = _collect_one(db, item, day, prefetched.get(item.machine_id))
        item.in_retry_queue = result != "success"
    db.flush()

    _refresh_counters(db, run)
    db.commit()
    db.refresh(run)

    log.info(
        "Coleta %s: status=%s total=%s ok=%s falhas=%s retry=%s",
        day, run.status, run.total_machines, run.success_count, run.failed_count, run.retry_count,
    )
    return run


def retry_pending(
    db: Session, collection_date: Optional[date] = None, respect_interval: bool = True
) -> Optional[DailyCollectionRun]:
    """Reprocessa apenas os teares que ficaram na fila de retentativa."""
    day = collection_date or get_yesterday()
    run = db.execute(
        select(DailyCollectionRun).where(DailyCollectionRun.collection_date == day)
    ).scalar_one_or_none()
    if run is None or run.retry_count == 0:
        return run

    pending = db.execute(
        select(DailyCollectionItem).where(
            DailyCollectionItem.run_id == run.id,
            DailyCollectionItem.in_retry_queue.is_(True),
        )
    ).scalars().all()

    now = datetime.utcnow()
    if respect_interval:
        due = [
            i for i in pending
            if i.last_retry_at is None or (now - i.last_retry_at) >= RETRY_INTERVAL
        ]
    else:
        due = pending
    if not due:
        return run

    run.status = "running"
    run.started_at = datetime.utcnow()
    prefetched = _fetch_many(db, due)
    for item in due:
        result = _collect_one(db, item, day, prefetched.get(item.machine_id))
        item.in_retry_queue = result != "success"
    db.flush()

    _refresh_counters(db, run)
    db.commit()
    db.refresh(run)
    return run


def ensure_daily_collection(db: Session, *, respect_hour: bool = True) -> Optional[DailyCollectionRun]:
    """Garante que a coleta do dia anterior exista e roda a retentativa pendente."""
    now = datetime.now()
    if respect_hour and now.hour < COLLECTION_HOUR:
        return None

    day = get_yesterday()
    run = db.execute(
        select(DailyCollectionRun).where(DailyCollectionRun.collection_date == day)
    ).scalar_one_or_none()

    if run is None:
        return collect_daily_data(db, day)
    if run.retry_count > 0:
        return retry_pending(db, day)
    return run
