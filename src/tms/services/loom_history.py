"""Paradas por causa a partir do histórico embutido no payload do tear.

O endpoint ``tms_get_monitor_data`` devolve, além do estado atual, a secção
``stop_history`` com os eventos ``MH_d<N>_h<H>_history START END CODE``.  Os
índices ``d0``/``d1`` referem-se aos dois dias anteriores ao dia corrente do
tear; ``MH_d<N>_tm`` informa a data-base de cada índice.

Este módulo converte esses eventos nos mesmos arrays de 12 categorias usados
pelo legado (``stop_ct``/``stop_tm``), permitindo preencher trama/urdume/outros
também para dias passados ainda retidos na memória do tear — sem confundir com
a leitura ao vivo.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import List, Optional

from tms.core.stopcodes import N_CATEGORIES, category_for_code
from tms.ingest.loom_file import LoomFile, LoomStopEvent

# Um único evento não pode durar mais que um dia (proteção contra relógio ruim).
MAX_EVENT_MIN = 24 * 60.0


@dataclass
class DayStops:
    """Agregado de paradas de um dia do histórico do tear."""

    counts: List[int] = field(default_factory=lambda: [0] * N_CATEGORIES)
    minutes: List[float] = field(default_factory=lambda: [0.0] * N_CATEGORIES)
    total_count: int = 0
    total_minutes: float = 0.0
    open_events: int = 0


@dataclass
class DayProduction:
    """Produção de um dia no bloco ``PM_yN_p5`` do payload do tear."""

    picks: float = 0.0
    meters: float = 0.0
    yards: float = 0.0
    run_minutes: float = 0.0
    stop_minutes: float = 0.0


def _event_minutes(event: LoomStopEvent, day: date) -> Optional[float]:
    """Duração do evento em minutos; ``None`` se o início/fim não existe."""
    if event.start is None or event.end is None:
        return None
    start = datetime.combine(day, event.start)
    end = datetime.combine(day, event.end)
    if end < start:
        # Evento que atravessou a meia-noite (raro no histórico diário).
        end += timedelta(days=1)
    minutes = (end - start).total_seconds() / 60.0
    if minutes < 0 or minutes > MAX_EVENT_MIN:
        return None
    return minutes


def day_stops(loom: LoomFile, day: date, mac_type: str = "JAT") -> Optional[DayStops]:
    """Agrega os eventos de parada do dia; ``None`` se o tear não tem o dia.

    Só considera os índices ``MH_d<N>`` (dias anteriores).  A secção ``MH_t``
    (dia corrente) é ignorada de propósito: uma coleta de dia passado nunca
    pode usar o estado atual do tear.
    """
    day_indexes = {
        index for index, start in loom.day_start.items() if start.date() == day
    }
    if not day_indexes:
        return None

    result = DayStops()
    for event in loom.stop_events:
        if event.day not in day_indexes:
            continue
        index = category_for_code(event.code, mac_type)
        result.counts[index] += 1
        result.total_count += 1
        duration = _event_minutes(event, day)
        if duration is None:
            result.open_events += 1
            continue
        result.minutes[index] += duration
        result.total_minutes += duration

    if result.total_count == 0:
        return None

    result.minutes = [round(value, 6) for value in result.minutes]
    result.total_minutes = round(result.total_minutes, 6)
    return result


def day_production(loom: LoomFile, day: date) -> Optional[DayProduction]:
    """Produção do dia, somando os turnos ``MJ_sN_yM``.

    A análise de pick ``PM_yN_p5_seisan`` nem sempre está habilitada no tear
    (há máquinas em que ela fica zerada enquanto ``MJ_*_seisan`` tem produção).
    Por isso a fonte principal são os turnos do dia; ``PM`` serve de fallback.
    Os valores crus seguem a mesma escala dos arquivos de turno do legado, que
    divide ``seisan`` por 10 ao gravar ``agg_shift``.  ``PM_t`` (dia corrente)
    nunca é usado para preencher um dia passado.
    """
    shift = loom.shift_days.get(day)
    if shift is None or not any(shift.seisan):
        shift = loom.pick_days.get(day)
    if shift is None or len(shift.seisan) < 2:
        return None

    def scaled(index: int) -> float:
        if index >= len(shift.seisan):
            return 0.0
        return round(shift.seisan[index] / 10.0, 3)

    stop_seconds = float(shift.to or 0)
    run_seconds = float(shift.rt or 0)
    # Nos blocos MJ/PM, `rt` é o tempo rodando e `to` é o tempo parado; juntos
    # cobrem o turno/dia (ex.: 32400 s = 9 h).
    return DayProduction(
        picks=scaled(0),
        meters=scaled(1),
        yards=scaled(2),
        run_minutes=round(run_seconds / 60.0, 3),
        stop_minutes=round(stop_seconds / 60.0, 3),
    )
