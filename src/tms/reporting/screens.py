"""Telas de relatório (Fase 3): efficiency, production e stop-analysis.

Espelha os CSVs/planilhas do legado:

- ``shift/efficiency.pm``: LOOM, STYLE, EFFIC%, RUN, STOP, WARP count + taxas, WEFT count + taxas;
- ``shift/production.pm``: LOOM, STYLE, PRODUCT = ``seisan[unit] + off_prod[unit]``;
- ``shift/stopanalysis.cgi``: colunas escolhidas pelo ``selitem`` (``report_prefs``)
  e coluna ``UNSELECT`` com o que não foi selecionado.

Modo loom/style (o legado também tem modo operador; não implementado aqui) e
períodos day/week/month. As taxas são recalculadas por hora de operação
(cph) e por dia (cpday = cph × 24); o legado deixava essas células em branco
para o Excel completar.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, List, Sequence

from tms.core.formulas import UNIT_NAMES, UNIT_PICK
from tms.reporting.periods import PeriodRow

# period_type do legado: shift=0, date=1, week=2, month=3
PERIOD_TYPE = {"day": 1, "week": 2, "month": 3}
PERIOD_LABEL = {"day": "DATE", "week": "WEEK", "month": "MONTH"}

TITLE_ITEM = (
    "WARP_TOP", "WARP", "FALS", "LENO_L", "LENO_R", "WEFT",
    "WARP_OUT", "DOFF", "MANUAL", "PWR_OFF", "OTHER",
)
TITLE_ITEM3 = ("CC_FRONT", "CC_REAR", "LENO")
TITLE_DETAIL = ("WF1", "WF2", "LH")
TITLE_COLOR = ("COLOR1", "COLOR2", "COLOR3", "COLOR4", "COLOR5", "COLOR6")


@dataclass
class Screen:
    header: List[str]
    rows: List[list] = field(default_factory=list)
    period_type: int = 0


def _at(values: Sequence, index: int) -> float:
    return values[index] if index < len(values) else 0


def _padded(values: Iterable, size: int = 12) -> List:
    out = list(values or [])[:size]
    return out + [0] * (size - len(out))


def _rate(count: float, run_minutes: float, *, per_day: bool = False) -> float:
    hours = run_minutes / 60.0
    if hours <= 0:
        return 0.0
    rate = count / hours
    return round(rate * 24.0, 3) if per_day else round(rate, 3)


# --------------------------------------------------------------- efficiency --

EFFICIENCY_COLUMNS = (
    "LOOM", "STYLE", "EFFIC&PERCENT", "RUN&MINUTE", "STOP&MINUTE",
    "WARP&COUNT", "WARP_RATE&CPH", "WARP_RATE&CPDAY",
    "WEFT&COUNT", "WEFT_RATE&CPH", "WEFT_RATE&CPDAY",
)


def warp_weft_counts(row: PeriodRow) -> tuple[int, int]:
    """``warp_ct`` e ``weft_ct`` como em `efficiency.pm`."""
    ct = _padded(row.stop_ct)
    warp = ct[0] + ct[1] + ct[2] + ct[3] + ct[4] + ct[11]
    return warp, ct[5]


def efficiency_screen(rows: Sequence[PeriodRow], period: str = "day") -> Screen:
    data = []
    for index, row in enumerate(rows, start=1):
        warp, weft = warp_weft_counts(row)
        data.append([
            index,
            row.mac_name,
            row.style or "",
            round(row.effic, 3),
            round(row.run_tm, 3),
            round(row.stop_ttm, 3),
            warp,
            _rate(warp, row.run_tm),
            _rate(warp, row.run_tm, per_day=True),
            weft,
            _rate(weft, row.run_tm),
            _rate(weft, row.run_tm, per_day=True),
        ])
    return Screen(
        header=[PERIOD_LABEL.get(period, period.upper()), *EFFICIENCY_COLUMNS],
        rows=data,
        period_type=PERIOD_TYPE.get(period, 0),
    )


# --------------------------------------------------------------- production --

def production_screen(
    rows: Sequence[PeriodRow], period: str = "day", unit: int = UNIT_PICK
) -> Screen:
    unit_title = UNIT_NAMES[unit] if 0 <= unit < len(UNIT_NAMES) else UNIT_NAMES[UNIT_PICK]
    data = [
        [index, row.mac_name, row.style or "", round(row.production(unit), 1)]
        for index, row in enumerate(rows, start=1)
    ]
    return Screen(
        header=[PERIOD_LABEL.get(period, period.upper()), "LOOM", "STYLE", f"PRODUCT&{unit_title}"],
        rows=data,
        period_type=PERIOD_TYPE.get(period, 0),
    )


# ------------------------------------------------------------ stop-analysis --

# especificações de coluna:
#   ("stop", i)         → stop_ct/tm[i]
#   ("wf1"|"wf2"|"lh", j) → array[i]
#   ("sum_stop", (i, j)) → soma de stop[i]+stop[j]
#   ("weft_other",)     → soma dos arrays wf/lh não selecionados
#   ("unsel",)          → tudo que ficou fora da seleção
ColumnSpec = tuple


def _stop_analysis_specs(prefs: dict, beam_type: int = 1) -> list[ColumnSpec]:
    item = list(prefs.get("item") or [])
    item3 = list(prefs.get("item3") or [])
    detail = list(prefs.get("detail") or [])
    color = list(prefs.get("color") or [])

    def v(seq, i):
        return int(seq[i]) if i < len(seq) else 0

    specs: list[ColumnSpec] = []
    unsel_stop: list[int] = []
    unsel_wf = {"wf1": [], "wf2": [], "lh": []}

    # item[0] WarpTop só existe em teares top-beam; senão é ignorado sem UNSELECT
    if v(item, 0):
        specs.append(("stop", 0, TITLE_ITEM[0]))
    elif beam_type == 2:
        unsel_stop.append(0)

    if v(item, 1):
        specs.append(("stop", 1, TITLE_ITEM[1]))
    else:
        unsel_stop.append(1)

    if v(item, 5):  # Weft
        if v(detail, 0) or v(detail, 1) or v(detail, 2):
            for d, name in enumerate(("wf1", "wf2", "lh")):
                for j in range(len(color)):
                    if v(detail, d) and v(color, j):
                        specs.append((name, j, f"{TITLE_DETAIL[d]}&{TITLE_COLOR[j]}"))
                    else:
                        unsel_wf[name].append(j)
            specs.append(("weft_other", unsel_wf, "WEFT_OTHER"))
        else:
            specs.append(("stop", 5, TITLE_ITEM[5]))
    else:
        unsel_stop.append(5)

    # CC / False selvage
    if v(item3, 0) or v(item3, 1):
        specs.append(("stop", 2, TITLE_ITEM3[0]))
        specs.append(("stop", 11, TITLE_ITEM3[1]))
    elif v(item, 2):
        specs.append(("sum_stop", (2, 11), TITLE_ITEM[2]))
    else:
        unsel_stop.extend([2, 11])

    # Leno
    if v(item, 3) or v(item, 4):
        specs.append(("stop", 3, TITLE_ITEM[3]))
        specs.append(("stop", 4, TITLE_ITEM[4]))
    elif v(item3, 2):
        specs.append(("sum_stop", (3, 4), TITLE_ITEM3[2]))
    else:
        unsel_stop.extend([3, 4])

    for i in range(6, 11):
        if v(item, i):
            specs.append(("stop", i, TITLE_ITEM[i]))
        else:
            unsel_stop.append(i)

    if unsel_stop or unsel_wf["wf1"] or unsel_wf["wf2"] or unsel_wf["lh"]:
        specs.append(("unsel", (unsel_stop, unsel_wf), "UNSELECT"))
    return specs


def _stop_analysis_value(row: PeriodRow, spec: ColumnSpec, *, time: bool) -> float:
    kind = spec[0]
    if kind == "stop":
        return _at(row.stop_tm if time else row.stop_ct, spec[1])
    if kind in ("wf1", "wf2", "lh"):
        source = getattr(row, f"{kind}_tm" if time else f"{kind}_ct")
        return _at(source, spec[1])
    if kind == "sum_stop":
        source = row.stop_tm if time else row.stop_ct
        return _at(source, spec[1][0]) + _at(source, spec[1][1])
    if kind == "weft_other":
        unsel_wf = spec[1]
        total = 0.0
        for name, indexes in unsel_wf.items():
            source = getattr(row, f"{name}_tm" if time else f"{name}_ct")
            total += sum(_at(source, j) for j in indexes)
        return total
    if kind == "unsel":
        unsel_stop, unsel_wf = spec[1]
        total = sum(_at(row.stop_tm if time else row.stop_ct, i) for i in unsel_stop)
        for name, indexes in unsel_wf.items():
            source = getattr(row, f"{name}_tm" if time else f"{name}_ct")
            total += sum(_at(source, j) for j in indexes)
        return total
    return 0


def stop_analysis_screen(
    rows: Sequence[PeriodRow],
    prefs: dict,
    *,
    period: str = "day",
    beam_type: int = 1,
    time: bool = False,
) -> Screen:
    """Uma saída de stop-analysis (``time=False`` = contagem, ``True`` = tempo)."""
    specs = _stop_analysis_specs(prefs, beam_type)
    header = [PERIOD_LABEL.get(period, period.upper()), "LOOM", "STYLE"]
    header += [spec[2] for spec in specs]

    data = []
    for index, row in enumerate(rows, start=1):
        line: list = [index, row.mac_name, row.style or ""]
        for spec in specs:
            value = _stop_analysis_value(row, spec, time=time)
            line.append(round(value, 3) if time else value)
        data.append(line)
    return Screen(header=header, rows=data, period_type=PERIOD_TYPE.get(period, 0))
