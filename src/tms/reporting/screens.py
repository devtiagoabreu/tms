"""Telas de relatório (Fase 3): efficiency, production, stop-analysis,
shiftreport e stylereport.

Espelha os CSVs/planilhas do legado:

- ``shift/efficiency.pm``: LOOM, STYLE, EFFIC%, RUN, STOP, WARP count + taxas, WEFT count + taxas;
- ``shift/production.pm``: LOOM, STYLE, PRODUCT = ``seisan[unit] + off_prod[unit]``;
- ``shift/stopanalysis.cgi``: colunas escolhidas pelo ``selitem`` (``report_prefs``)
  e coluna ``UNSELECT`` com o que não foi selecionado;
- ``shift/shiftreport.pm``: relatório de turno (item2/item/item3/detail/color
  do selitem, totais e UNSELECT/UNSELECT2);
- ``shift/stylereport.cgi``: total por estilo (LOOM_COUNT = nº de teares).

Modo tear/estilo (``mode="shift"``), operador (``mode="operator"``, agrega
`operator_daily` por operador; sem granularidade de turno) e estilo
(``mode="style"``, agrega por estilo em `agg_shift`); períodos
shift/day/week/month. As taxas (``RATE_PH``, ``RATE_PDAY``, ``RATE_PP``) são
recalculadas por hora de operação e por 1000 picks; o legado deixava essas
células em branco para o Excel completar (``RATE_PP`` = paradas ÷ produção
da unidade; ``RATE_PDAY`` = ``RATE_PH × 24``).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Iterable, List, Sequence

from tms.core.formulas import UNIT_NAMES, UNIT_PICK
from tms.reporting.periods import PeriodRow

# period_type do legado: shift=0, date=1, week=2, month=3
PERIOD_TYPE = {"shift": 0, "day": 1, "week": 2, "month": 3}
PERIOD_LABEL = {"shift": "SHIFT", "day": "DATE", "week": "WEEK", "month": "MONTH"}

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

OPERATOR_COLUMNS = (
    "OPERATOR", "EFFIC&PERCENT", "RUN&MINUTE", "STOP&MINUTE",
    "WARP&COUNT", "WARP_RATE&CPH", "WARP_RATE&CPDAY",
    "WEFT&COUNT", "WEFT_RATE&CPH", "WEFT_RATE&CPDAY",
)


def warp_weft_counts(row: PeriodRow) -> tuple[int, int]:
    """``warp_ct`` e ``weft_ct`` como em `efficiency.pm`."""
    ct = _padded(row.stop_ct)
    warp = ct[0] + ct[1] + ct[2] + ct[3] + ct[4] + ct[11]
    return warp, ct[5]


def efficiency_screen(
    rows: Sequence[PeriodRow], period: str = "day", mode: str = "shift"
) -> Screen:
    operator = mode == "operator"
    data = []
    for index, row in enumerate(rows, start=1):
        warp, weft = warp_weft_counts(row)
        ident = [row.operator or ""] if operator else [row.mac_name, row.style or ""]
        data.append([
            index,
            *ident,
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
    columns = OPERATOR_COLUMNS if operator else EFFICIENCY_COLUMNS
    return Screen(
        header=[PERIOD_LABEL.get(period, period.upper()), *columns],
        rows=data,
        period_type=PERIOD_TYPE.get(period, 0),
    )


# --------------------------------------------------------------- production --

def production_screen(
    rows: Sequence[PeriodRow],
    period: str = "day",
    unit: int = UNIT_PICK,
    mode: str = "shift",
) -> Screen:
    operator = mode == "operator"
    unit_title = UNIT_NAMES[unit] if 0 <= unit < len(UNIT_NAMES) else UNIT_NAMES[UNIT_PICK]
    data = []
    for index, row in enumerate(rows, start=1):
        ident = [row.operator or ""] if operator else [row.mac_name, row.style or ""]
        data.append([index, *ident, round(row.production(unit), 1)])
    columns = ("OPERATOR", f"PRODUCT&{unit_title}") if operator else (
        "LOOM", "STYLE", f"PRODUCT&{unit_title}"
    )
    return Screen(
        header=[PERIOD_LABEL.get(period, period.upper()), *columns],
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
    mode: str = "shift",
) -> Screen:
    """Uma saída de stop-analysis (``time=False`` = contagem, ``True`` = tempo).

    ``mode="operator"`` troca LOOM/STYLE por OPERATOR (agregado por operador).
    """
    specs = _stop_analysis_specs(prefs, beam_type)
    ident = ["OPERATOR"] if mode == "operator" else ["LOOM", "STYLE"]
    header = [PERIOD_LABEL.get(period, period.upper()), *ident]
    header += [spec[2] for spec in specs]

    data = []
    for index, row in enumerate(rows, start=1):
        values = [row.operator or ""] if mode == "operator" else [
            row.mac_name, row.style or ""
        ]
        line: list = [index, *values]
        for spec in specs:
            value = _stop_analysis_value(row, spec, time=time)
            line.append(round(value, 3) if time else value)
        data.append(line)
    return Screen(header=header, rows=data, period_type=PERIOD_TYPE.get(period, 0))


# -------------------------------------------------------------- shiftreport --

TITLE_ITEM2 = (
    "TOP_BEAM", "BEAM", "RPM", "EFFIC&PERCENT",
    "RUN&MINUTE", "STOP&MINUTE", "PRODUCT",
)

MISS_RATE_NAMES = ("RATE_PH", "RATE_PDAY", "RATE_PP")


@dataclass
class _Clause:
    """Grupo de colunas do shift/stylereport: cabeçalho + valores por linha."""

    header: List[str]
    values: Callable[[PeriodRow], list]


def _miss_rates(count: float, row: PeriodRow, unit: int) -> list:
    """RATE_PH/RATE_PDAY/RATE_PP de um contador de paradas.

    O legado deixava essas células em branco para o Excel; aqui:
    ``RATE_PH = count / horas``, ``RATE_PDAY = RATE_PH × 24`` e
    ``RATE_PP = count / produção(unit)`` (por 1000 picks quando unit=PICK).
    """
    hours = row.run_tm / 60.0
    if hours > 0:
        ph = round(count / hours, 3)
        pday = round(ph * 24.0, 3)
    else:
        ph = pday = 0.0
    prod = row.production(unit)
    pp = round(count / prod, 3) if prod else 0.0
    return [ph, pday, pp]


def _item2_clauses(prefs: dict, unit: int) -> List[_Clause]:
    """Colunas do item2 (Top Beam/Beam/RPM/Effic) + RUN/STOP/PROD.

    RUN/STOP/PRODUCT&PICK são sempre emitidos (como no legado); PROD da
    unidade só quando ``item2[6]``.
    """
    item2 = list(prefs.get("item2") or [])

    def v(i: int) -> int:
        return int(item2[i]) if i < len(item2) else 0

    unit_title = UNIT_NAMES[unit] if 0 <= unit < len(UNIT_NAMES) else UNIT_NAMES[UNIT_PICK]
    clauses: List[_Clause] = []
    if v(0):
        clauses.append(_Clause(["TOP_BEAM"], lambda r: [r.ubeam or ""]))
    if v(1):
        clauses.append(_Clause(["BEAM"], lambda r: [r.beam or ""]))
    if v(2):
        clauses.append(_Clause(["RPM"], lambda r: [round(r.rpm, 3)]))
    if v(3):
        clauses.append(_Clause(["EFFIC&PERCENT"], lambda r: [round(r.effic, 3)]))
    clauses.append(_Clause(["RUN&MINUTE"], lambda r: [round(r.run_tm, 3)]))
    clauses.append(_Clause(["STOP&MINUTE"], lambda r: [round(r.stop_ttm, 3)]))
    clauses.append(_Clause(["PRODUCT&PICK"], lambda r: [round(_at(r.seisan, 0), 3)]))
    if v(6):
        clauses.append(_Clause(
            [f"PRODUCT&{unit_title}"], lambda r: [round(r.production(unit), 1)],
        ))
    return clauses


def _stops_clauses(prefs: dict, *, beam_type: int, unit: int) -> List[_Clause]:
    """Seção de paradas (main: mac/warp/weft/false/leno; unselect; totais;
    detail: WF1/2/LH×cor, CC Front/Back, Leno L/R); ordem = shiftreport.pm."""
    item = list(prefs.get("item") or [])
    item3 = list(prefs.get("item3") or [])
    detail = list(prefs.get("detail") or [])
    color = list(prefs.get("color") or [])

    def v(seq: List, i: int) -> int:
        return int(seq[i]) if i < len(seq) else 0

    def stop_clause(name: str, idx: int, rates: bool = False) -> _Clause:
        header = [f"{name}&COUNT", f"{name}&MINUTE"]
        if rates:
            header += [f"{name}&{r}" for r in MISS_RATE_NAMES]

        def values(row: PeriodRow) -> list:
            count = int(_at(row.stop_ct, idx))
            line = [count, round(_at(row.stop_tm, idx), 3)]
            if rates:
                line += _miss_rates(count, row, unit)
            return line

        return _Clause(header, values)

    def yarn_clause(name: str, idxs: Sequence[int]) -> _Clause:
        header = [f"{name}&COUNT", f"{name}&MINUTE"]
        header += [f"{name}&{r}" for r in MISS_RATE_NAMES]

        def values(row: PeriodRow) -> list:
            count = int(sum(_at(row.stop_ct, i) for i in idxs))
            return [count, round(sum(_at(row.stop_tm, i) for i in idxs), 3),
                    *_miss_rates(count, row, unit)]

        return _Clause(header, values)

    def wf_clause(name: str, ct_attr: str, tm_attr: str, j: int) -> _Clause:
        header = [f"{name}&COUNT", f"{name}&MINUTE"]
        header += [f"{name}&{r}" for r in MISS_RATE_NAMES]

        def values(row: PeriodRow) -> list:
            count = int(_at(getattr(row, ct_attr), j))
            return [count, round(_at(getattr(row, tm_attr), j), 3),
                    *_miss_rates(count, row, unit)]

        return _Clause(header, values)

    warp0_sel = bool(v(item, 0))
    warp0_included = warp0_sel or beam_type == 2
    warp1_sel = bool(v(item, 1))
    weft_sel = bool(v(item, 5))
    false_sel = bool(v(item, 2))
    leno_sel = bool(v(item3, 2))

    clauses: List[_Clause] = []
    for i in range(6, 11):  # WarpOut..Other
        if v(item, i):
            clauses.append(stop_clause(TITLE_ITEM[i], i))
    for i in range(0, 2):  # WarpTop, Warp
        if v(item, i):
            clauses.append(yarn_clause(TITLE_ITEM[i], (i,)))
    if weft_sel:
        clauses.append(yarn_clause(TITLE_ITEM[5], (5,)))
    if false_sel:  # False / CC Total
        clauses.append(yarn_clause(TITLE_ITEM[2], (2, 11)))
    if leno_sel:  # Leno Total
        clauses.append(yarn_clause(TITLE_ITEM3[2], (3, 4)))

    # unselect/unselect2/total (somas por linha, regra de WarpTop do legado)
    def unselected(row: PeriodRow) -> tuple[float, float]:
        count = time_ = 0.0
        if warp0_included and not warp0_sel:
            count += _at(row.stop_ct, 0)
            time_ += _at(row.stop_tm, 0)
        if not warp1_sel:
            count += _at(row.stop_ct, 1)
            time_ += _at(row.stop_tm, 1)
        if not weft_sel:
            count += _at(row.stop_ct, 5)
            time_ += _at(row.stop_tm, 5)
        if not false_sel:
            count += _at(row.stop_ct, 2) + _at(row.stop_ct, 11)
            time_ += _at(row.stop_tm, 2) + _at(row.stop_tm, 11)
        if not leno_sel:
            count += _at(row.stop_ct, 3) + _at(row.stop_ct, 4)
            time_ += _at(row.stop_tm, 3) + _at(row.stop_tm, 4)
        for i in range(6, 11):
            if not v(item, i):
                count += _at(row.stop_ct, i)
                time_ += _at(row.stop_tm, i)
        return count, time_

    def unselected2(row: PeriodRow) -> float:
        count = 0.0
        if warp0_included and not warp0_sel:
            count += _at(row.stop_ct, 0)
        if not warp1_sel:
            count += _at(row.stop_ct, 1)
        if not weft_sel:
            count += _at(row.stop_ct, 5)
        if not false_sel:
            count += _at(row.stop_ct, 2) + _at(row.stop_ct, 11)
        if not leno_sel:
            count += _at(row.stop_ct, 3) + _at(row.stop_ct, 4)
        return count

    has_unsel = (
        any(not v(item, i) for i in range(6, 11))
        or (warp0_included and not warp0_sel) or not warp1_sel
        or not weft_sel or not false_sel or not leno_sel
    )
    has_unsel2 = (
        (warp0_included and not warp0_sel) or not warp1_sel
        or not weft_sel or not false_sel or not leno_sel
    )

    if has_unsel:
        clauses.append(_Clause(["UNSELECT&COUNT", "UNSELECT&MINUTE"], lambda r: [
            int(unselected(r)[0]), round(unselected(r)[1], 3),
        ]))
    if has_unsel2:
        clauses.append(_Clause(
            ["UNSELECT2&COUNT", *[f"UNSELECT&{n}" for n in MISS_RATE_NAMES]],
            lambda r: [int(unselected2(r)), *_miss_rates(unselected2(r), r, unit)],
        ))

    def total_values(row: PeriodRow) -> list:
        total_ct = row.total_ct(beam_type)
        total_tm = sum(_at(row.stop_tm, i) for i in range(12))
        if beam_type != 2:
            total_tm -= _at(row.stop_tm, 0)
        return [total_ct, round(total_tm, 3), row.total2_ct(beam_type),
                *_miss_rates(total_ct, row, unit)]

    clauses.append(_Clause(
        ["TOTAL&COUNT", "TOTAL&MINUTE", "TOTAL2&COUNT",
         *[f"TOTAL&{n}" for n in MISS_RATE_NAMES]],
        total_values,
    ))

    # detail: WF1/WF2/LH × cor
    wf_attrs = (("wf1_ct", "wf1_tm"), ("wf2_ct", "wf2_tm"), ("lh_ct", "lh_tm"))
    for d, dname in enumerate(TITLE_DETAIL):
        if v(detail, d):
            ct_attr, tm_attr = wf_attrs[d]
            for j in range(len(color)):
                if v(color, j):
                    clauses.append(wf_clause(
                        f"{dname}&{TITLE_COLOR[j]}", ct_attr, tm_attr, j,
                    ))
    # CC Front / CC Back (o legado do stylereport usava stop[3] por engano)
    if v(item3, 0):
        clauses.append(yarn_clause(TITLE_ITEM3[0], (2,)))
    if v(item3, 1):
        clauses.append(yarn_clause(TITLE_ITEM3[1], (11,)))
    # Leno(L) / Leno(R)
    for i in (3, 4):
        if v(item, i):
            clauses.append(yarn_clause(TITLE_ITEM[i], (i,)))
    return clauses


def _report_screen(
    rows: Sequence[PeriodRow],
    ident_header: List[str],
    ident_values: Callable[[PeriodRow], list],
    clauses: Sequence[_Clause],
    period: str,
) -> Screen:
    header = [PERIOD_LABEL.get(period, period.upper()), *ident_header]
    for clause in clauses:
        header.extend(clause.header)
    data = []
    for index, row in enumerate(rows, start=1):
        line: list = [index]
        line.extend(ident_values(row))
        for clause in clauses:
            line.extend(clause.values(row))
        data.append(line)
    return Screen(header=header, rows=data, period_type=PERIOD_TYPE.get(period, 0))


def shiftreport_screen(
    rows: Sequence[PeriodRow],
    prefs: dict,
    *,
    period: str = "day",
    sel: str = "loom",
    beam_type: int = 1,
    unit: int = UNIT_PICK,
    mode: str = "shift",
    jat_ari: bool = True,
    lwt_ari: bool = True,
) -> Screen:
    """Relatório de turno: ident + item2 + paradas + totais.

    ``mode="operator"`` mostra só OPERATOR (agregado por operador, sem teares);
    ``sel="loom"|"style"`` ordena LOOM/STYLE (MAC_TYPE quando JAT e LWT existem).
    """
    clauses = _item2_clauses(prefs, unit) + _stops_clauses(
        prefs, beam_type=beam_type, unit=unit
    )
    if mode == "operator":
        ident_header, ident_values = ["OPERATOR"], (lambda r: [r.operator or ""])
    elif sel == "loom":
        if jat_ari and lwt_ari:
            ident_header = ["LOOM", "MAC_TYPE", "STYLE"]
            ident_values = lambda r: [r.mac_name, r.mac_type, r.style or ""]
        else:
            ident_header = ["LOOM", "STYLE"]
            ident_values = lambda r: [r.mac_name, r.style or ""]
    else:
        if jat_ari and lwt_ari:
            ident_header = ["STYLE", "LOOM", "MAC_TYPE"]
            ident_values = lambda r: [r.style or "", r.mac_name, r.mac_type]
        else:
            ident_header = ["STYLE", "LOOM"]
            ident_values = lambda r: [r.style or "", r.mac_name]
    return _report_screen(rows, ident_header, ident_values, clauses, period)


def stylereport_screen(
    rows: Sequence[PeriodRow],
    prefs: dict,
    *,
    period: str = "day",
    beam_type: int = 1,
    unit: int = UNIT_PICK,
) -> Screen:
    """Total por estilo (linhas já agregadas por estilo, ``mode="style"``).

    ``LOOM_COUNT`` = nº de teares distintos do estilo no período; no legado o
    Excel completava essa coluna.
    """
    clauses = _item2_clauses(prefs, unit) + _stops_clauses(
        prefs, beam_type=beam_type, unit=unit
    )
    return _report_screen(
        rows,
        ["LOOM", "SORTKEY", "STYLE", "LOOM_COUNT"],
        lambda r: ["", "", r.style or "", r.loom_count],
        clauses,
        period,
    )
