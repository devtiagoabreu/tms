"""Exportação CSV dos relatórios de período (Fase 3).

Layout estável (não o dinâmico do selitem legado): identidade, métricas,
produção e as 12 categorias de parada (contagem + minutos) + totais. Os arrays
WF1/WF2/LH vão como campos separados por ``;`` para caber em uma célula.
"""

from __future__ import annotations

import csv
import io
from typing import Iterable, List

from tms.core.formulas import UNIT_PICK
from tms.core.stopcodes import CATEGORY_KEYS
from tms.reporting.periods import PeriodRow

IDENTITY = ("period", "key", "mac_name", "mac_type", "style", "beam", "ubeam")
METRICS = ("rpm", "effic", "run_tm", "stop_ttm")
PRODUCTION = (
    "seisan_1", "seisan_2", "seisan_3",
    "off_prod_1", "off_prod_2", "off_prod_3",
    "production", "pick",
)
TOTALS = ("total_ct", "total2_ct", "wf1_ct", "wf1_tm", "wf2_ct", "wf2_tm", "lh_ct", "lh_tm")


def header() -> List[str]:
    cols = list(IDENTITY) + list(METRICS) + list(PRODUCTION)
    cols += [f"ct_{key}" for key in CATEGORY_KEYS]
    cols += [f"tm_{key}" for key in CATEGORY_KEYS]
    cols += list(TOTALS)
    return cols


def _fmt(value: float | int | None, nd: int = 2) -> str:
    if value is None:
        return ""
    if isinstance(value, int):
        return str(value)
    return f"{value:.{nd}f}"


def _join(values: Iterable[float | int]) -> str:
    return ";".join(_fmt(v) for v in values)


def row_values(row: PeriodRow, *, unit: int = UNIT_PICK, beam_type: int = 1) -> List[str]:
    seisan = list(row.seisan) + [0.0] * (3 - len(row.seisan))
    off_prod = list(row.off_prod) + [0.0] * (3 - len(row.off_prod))
    values: List[str] = [
        row.period,
        row.key,
        row.mac_name,
        row.mac_type,
        row.style or "",
        row.beam or "",
        row.ubeam or "",
        _fmt(row.rpm),
        _fmt(row.effic),
        _fmt(row.run_tm, 3),
        _fmt(row.stop_ttm, 3),
        _fmt(seisan[0], 1),
        _fmt(seisan[1], 1),
        _fmt(seisan[2], 1),
        _fmt(off_prod[0], 1),
        _fmt(off_prod[1], 1),
        _fmt(off_prod[2], 1),
        _fmt(row.production(unit), 1),
        _fmt(seisan[0], 1),  # pick = seisan[0]
    ]
    values += [str(v) for v in row.stop_ct]
    values += [_fmt(v, 3) for v in row.stop_tm]
    values += [
        str(row.total_ct(beam_type)),
        str(row.total2_ct(beam_type)),
        _join(row.wf1_ct),
        _join(row.wf1_tm),
        _join(row.wf2_ct),
        _join(row.wf2_tm),
        _join(row.lh_ct),
        _join(row.lh_tm),
    ]
    return values


def write_csv(
    rows: Iterable[PeriodRow],
    *,
    unit: int = UNIT_PICK,
    beam_type: int = 1,
    delimiter: str = ",",
) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=delimiter, lineterminator="\r\n")
    writer.writerow(header())
    for row in rows:
        writer.writerow(row_values(row, unit=unit, beam_type=beam_type))
    return buffer.getvalue()
