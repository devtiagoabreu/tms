"""Totais mensais de produção (metros e pontos) para o dashboard.

A fonte principal é ``daily_loom_data`` (coleta diária).  Para meses anteriores
ao início da coleta, o legado deixou exports em ``C:\\TMSDATA\\<yyyy>-<mm>\\daily``
com uma linha por tear/turno; nesses arquivos a coluna 5 é a produção de pick
(pontos) e a coluna 10 é a produção em metros, já na mesma escala usada pelo
restante do TMS.

Tears duplos (``machines.is_double``) produzem o dobro de metros e pontos,
então ``metros_reais`` e ``pontos_reais`` levam esse multiplicador em conta.
"""

from __future__ import annotations

import csv
import os
from datetime import date, timedelta
from pathlib import Path

from sqlalchemy import select, func
from sqlalchemy.orm import Session

from tms.models.daily import DailyLoomData
from tms.models.masters import Machine

LEGACY_ROOT = Path(os.getenv("TMS_LEGACY_EXPORT_DIR", r"C:\TMSDATA"))


def _empty(start: date, end: date) -> dict:
    return {
        "start": start,
        "end": end,
        "meters": 0.0,
        "points": 0.0,
        "days": 0,
        "source": None,
    }


def _legacy_csv_summary(start: date, end: date) -> dict | None:
    """Soma os exports legados do mês, se existirem no disco."""
    if start.year != end.year or start.month != end.month:
        return None
    directory = LEGACY_ROOT / f"{start:%Y-%m}" / "daily"
    if not directory.is_dir():
        return None

    meters = 0.0
    points = 0.0
    days: set[date] = set()
    found = False
    for path in sorted(directory.glob("*.csv")):
        try:
            with path.open("r", encoding="utf-8-sig", newline="") as handle:
                for row in csv.reader(handle):
                    if len(row) < 12:
                        continue
                    period = (row[0] or "").strip()
                    try:
                        # 2026.10.02.A -> 2026-10-02
                        day = date.fromisoformat(period[:10].replace(".", "-"))
                    except ValueError:
                        continue
                    if not (start <= day <= end):
                        continue
                    try:
                        points += float(row[5])
                        meters += float(row[10])
                    except (TypeError, ValueError):
                        continue
                    days.add(day)
                    found = True
        except OSError:
            continue

    if not found:
        return None
    return {
        "start": start,
        "end": end,
        "meters": round(meters, 1),
        "points": round(points, 1),
        "days": len(days),
        "source": "legacy_csv",
    }


def month_summary(
    db: Session,
    start: date,
    end: date,
    *,
    allow_legacy: bool = True,
) -> dict:
    """Soma metros_reais e pontos_reais do intervalo.

    ``metros_reais`` = ``meters`` × (2 se tear duplo, senão 1)
    ``pontos_reais`` = (``picks`` × 10) × (2 se tear duplo, senão 1)

    Usa o export legado como fallback quando não houver dados diários.
    """
    rows = list(
        db.execute(
            select(
                DailyLoomData,
                Machine.is_double,
            )
            .outerjoin(Machine, Machine.mac_name == DailyLoomData.mac_name)
            .where(
                DailyLoomData.collection_date >= start,
                DailyLoomData.collection_date <= end,
            )
        ).all()
    )
    has_values = any(
        r.DailyLoomData.meters is not None
        or r.DailyLoomData.picks is not None
        or r.DailyLoomData.pontos_reais is not None
        for r in rows
    )
    if rows and has_values:
        meters_reais_total = 0.0
        pontos_reais_total = 0.0
        for row in rows:
            r = row.DailyLoomData
            is_double = bool(row.is_double) if row.is_double is not None else False
            multiplicador = 2.0 if is_double else 1.0

            if r.meters is not None:
                meters_reais_total += float(r.meters) * multiplicador
            if r.pontos_reais is not None:
                pontos_reais_total += float(r.pontos_reais) * multiplicador
            elif r.picks is not None:
                pontos_reais_total += float(r.picks) * 10 * multiplicador

        return {
            "start": start,
            "end": end,
            "meters": round(meters_reais_total, 1),
            "points": round(pontos_reais_total, 1),
            "days": len({r.DailyLoomData.collection_date for r in rows}),
            "source": "daily",
        }

    if allow_legacy:
        legacy = _legacy_csv_summary(start, end)
        if legacy is not None:
            return legacy
    return _empty(start, end)


def current_and_previous_months(today: date | None = None) -> tuple[tuple[date, date], tuple[date, date]]:
    """Intervalos fechados do mês atual e do mês anterior."""
    today = today or date.today()
    current_start = today.replace(day=1)
    previous_end = current_start - timedelta(days=1)
    previous_start = previous_end.replace(day=1)
    return (current_start, today), (previous_start, previous_end)
