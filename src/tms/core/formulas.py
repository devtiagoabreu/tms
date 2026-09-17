"""Fórmulas canônicas dos relatórios (ver docs/migracao/03-camada-relatorios.md).

No legado, RPM/EFFIC/taxas eram computadas pelo template Excel; o exportcsv2.cgi
guardava as definições. Aqui ficam do lado do servidor.
"""

from __future__ import annotations

from typing import Sequence

# Unidades de produção — índice coincide com selitem unit.
UNIT_PICK = 0
UNIT_METER = 1
UNIT_YARD = 2

UNIT_NAMES = ("PICK", "METER", "YARD")


def rpm(seisan_0: float, run_tm: float) -> float:
    """RPM a partir de unidades CRUAS: seisan[0] em décimos, run_tm em segundos.

    RPM = seisan[0]*100 / (run_tm/60). Para valores já agregados (seisan /10 e
    run_tm em minutos) use :func:`rpm_from_agg`.
    """
    if run_tm <= 0:
        return 0.0
    return seisan_0 * 100.0 / (run_tm / 60.0)


def rpm_from_agg(seisan_final_0: float, run_min: float) -> float:
    """RPM a partir de valores agregados: seisan/10 e run_tm em minutos.

    Equivale a ``rpm(seisan_final_0*10, run_min*60)`` → ``1000*seisan/run_min``.
    """
    if run_min <= 0:
        return 0.0
    return 1000.0 * seisan_final_0 / run_min


def effic(run_tm: float, stop_ttm: float) -> float:
    """EFFIC% = run_tm*100 / (run_tm + stop_ttm)."""
    total = run_tm + stop_ttm
    if total <= 0:
        return 0.0
    return run_tm * 100.0 / total


def production(seisan: Sequence[float], off_prod: Sequence[float], unit: int = UNIT_PICK) -> float:
    """Production(unit) = seisan[unit] + off_prod[unit].

    Runs do legado: off_prod default (0,0,0) quando ausente.
    """
    if unit < 0 or unit > 2:
        raise ValueError(f"unit inválida: {unit}")
    op = off_prod[unit] if unit < len(off_prod) else 0.0
    sp = seisan[unit] if unit < len(seisan) else 0.0
    return sp + op


def false_cc_total(stop_ct: Sequence[int]) -> int:
    """False/CC Total = stop_ct[2] + stop_ct[11] (shiftreport)."""
    return stop_ct[2] + stop_ct[11]


def leno_total(stop_ct: Sequence[int]) -> int:
    """Leno Total = stop_ct[3] + stop_ct[4] (shiftreport)."""
    return stop_ct[3] + stop_ct[4]


def warp_ct(stop_ct: Sequence[int]) -> int:
    """warp_ct (efficiency report) = stop_ct[0..4] + stop_ct[11]."""
    return sum(stop_ct[0:5]) + stop_ct[11]


def weft_ct(stop_ct: Sequence[int]) -> int:
    """weft_ct (efficiency report) = stop_ct[5]."""
    return stop_ct[5]


def shiftreport_total(stop_ct: Sequence[int], beam_type: int = 1) -> int:
    """total_ct: soma das 12 categorias com colapsos false/leno.

    stop_ct[0] (Warp(Top)) é excluído quando beam_type != 2.
    """
    total = sum(stop_ct)
    if beam_type != 2:
        total -= stop_ct[0]
    return total


def shiftreport_total2(stop_ct: Sequence[int], beam_type: int = 1) -> int:
    """total2_ct: apenas fiação (warp + weft + false + leno)."""
    total = stop_ct[0] + stop_ct[1] + stop_ct[5] + false_cc_total(stop_ct) + leno_total(stop_ct)
    if beam_type != 2:
        total -= stop_ct[0]
    return total


def svs_pick(seisan_0: float) -> float:
    """PRODUCT&PICK (svsreport) = 1000 * seisan[0]."""
    return 1000.0 * seisan_0


def svs_other(stop_ct: Sequence[int], lh_ct: Sequence[int]) -> int:
    """other (svsreport) = sum(stop_ct[2..4]) + stop_ct[11] + sum(lh_ct)."""
    return sum(stop_ct[2:5]) + stop_ct[11] + sum(lh_ct)


def format_minutes(value: float) -> str:
    """Minutos agregados com %1.2f (espelha exportcsv2.cgi)."""
    return f"{value:.2f}"


def format_seisan(value: float) -> str:
    """seisan/10 → %1.1f (espelha exportcsv2.cgi)."""
    return f"{value:.1f}"