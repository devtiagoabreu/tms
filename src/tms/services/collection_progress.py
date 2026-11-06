"""Andamento em memoria da coleta diaria.

A coleta roda dentro da propria requisicao HTTP (endpoint sincrono), mas o
navegador consulta o andamento em paralelo enquanto espera a resposta. Guardar o
estado em memoria e suficiente: ele existe apenas para alimentar a barra de
progresso e e reiniciado a cada nova coleta.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from threading import Lock
from typing import Optional

# Fases exibidas na interface.
PHASE_FETCHING = "fetching"
PHASE_PROCESSING = "processing"
PHASE_DONE = "done"

_RUNNING_STATUSES = {"idle", "running"}


@dataclass
class _Progress:
    collection_date: date
    status: str = "idle"
    phase: str = "idle"
    total: int = 0
    fetched: int = 0
    processed: int = 0
    success_count: int = 0
    failed_count: int = 0
    message: str = ""
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None


_lock = Lock()
_progress: dict[date, _Progress] = {}


def _iso(value: Optional[datetime]) -> Optional[str]:
    return value.isoformat() if value else None


def _percent(entry: _Progress) -> int:
    if entry.status not in _RUNNING_STATUSES:
        return 100
    if entry.total <= 0:
        return 0
    # Cada tear custa duas etapas: leitura (rede) e processamento (banco).
    done = min(entry.fetched, entry.total) + min(entry.processed, entry.total)
    return max(0, min(100, round(done * 100 / (entry.total * 2))))


def _find(day: date) -> Optional[_Progress]:
    return _progress.get(day)


def start(day: date, total: int) -> None:
    """Inicia (ou reinicia) o acompanhamento de uma coleta."""
    with _lock:
        entry = _Progress(
            collection_date=day,
            status="running",
            phase=PHASE_FETCHING,
            total=max(total, 0),
            message="Lendo os teares…",
            started_at=datetime.utcnow(),
        )
        _progress[day] = entry


def set_phase(day: date, phase: str, message: str) -> None:
    with _lock:
        entry = _find(day)
        if entry is None:
            return
        entry.phase = phase
        entry.message = message


def fetch_completed(day: date, done: int, total: int, mac_name: str) -> None:
    with _lock:
        entry = _find(day)
        if entry is None:
            return
        entry.phase = PHASE_FETCHING
        entry.fetched = done
        entry.total = total
        entry.message = f"Lendo tear {mac_name} ({done}/{total})"


def process_completed(day: date, done: int, total: int, mac_name: str, result: str) -> None:
    with _lock:
        entry = _find(day)
        if entry is None:
            return
        entry.phase = PHASE_PROCESSING
        entry.processed = done
        entry.total = total
        if result == "success":
            entry.success_count += 1
        else:
            entry.failed_count += 1
        entry.message = f"Processando tear {mac_name} ({done}/{total})"


def finish(
    day: date,
    status: str,
    success_count: int,
    failed_count: int,
    message: str,
) -> None:
    with _lock:
        entry = _find(day)
        if entry is None:
            return
        entry.status = status
        entry.phase = PHASE_DONE
        entry.fetched = entry.total
        entry.processed = entry.total
        entry.success_count = success_count
        entry.failed_count = failed_count
        entry.message = message
        entry.finished_at = datetime.utcnow()


def snapshot(day: date) -> dict:
    """Retorna o andamento atual em formato serializavel."""
    with _lock:
        entry = _find(day)
        if entry is None:
            return {
                "collection_date": day.isoformat(),
                "status": "idle",
                "phase": "idle",
                "total": 0,
                "fetched": 0,
                "processed": 0,
                "success_count": 0,
                "failed_count": 0,
                "percent": 0,
                "message": "Nenhuma coleta em andamento.",
                "started_at": None,
                "finished_at": None,
            }
        return {
            "collection_date": entry.collection_date.isoformat(),
            "status": entry.status,
            "phase": entry.phase,
            "total": entry.total,
            "fetched": entry.fetched,
            "processed": entry.processed,
            "success_count": entry.success_count,
            "failed_count": entry.failed_count,
            "percent": _percent(entry),
            "message": entry.message,
            "started_at": _iso(entry.started_at),
            "finished_at": _iso(entry.finished_at),
        }


def reset(day: Optional[date] = None) -> None:
    """Limpa o estado (usado em testes e ao reiniciar uma coleta manual)."""
    with _lock:
        if day is None:
            _progress.clear()
        else:
            _progress.pop(day, None)
