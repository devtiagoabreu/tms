"""Códigos de parada: mapeamento cru (40/31) → 12 categorias.

Espelha `common/TMScommon.pm` -> get_detail_stop_jat / get_detail_stop_lwt
(ver docs/migracao/02-modelo-de-dados.md).
"""

from __future__ import annotations

from typing import Dict, List, Sequence

JAT = "JAT"
LWT = "LWT"

N_CATEGORIES = 12

# Índices das 12 categorias finais (arrays stop_ct/stop_tm agregados).
CATEGORY_KEYS: List[str] = [
    "WARP_TOP_MISS",     # 0
    "WARP_MISS",         # 1
    "FALSE_SELVAGE_MISS",  # 2
    "LENO_L_MISS",       # 3
    "LENO_R_MISS",       # 4
    "WEFT_MISS",         # 5
    "WARP_OUT",          # 6
    "CLOTH_DOFFING",     # 7
    "MANUAL_STOP",       # 8
    "POWER_OFF",         # 9
    "OTHER_STOP",        # 10
    "CC_BACK",           # 11
]

# Rótulos por idioma (chave da categoria). Os mesmos valores dos str_*.pm.
CATEGORY_LABELS: Dict[str, Dict[str, str]] = {
    "en": {
        "WARP_TOP_MISS": "Warp(Top)",
        "WARP_MISS": "Warp",
        "FALSE_SELVAGE_MISS": "False selvage",
        "LENO_L_MISS": "Leno(Left)",
        "LENO_R_MISS": "Leno(Right)",
        "WEFT_MISS": "Weft",
        "WARP_OUT": "Warp out",
        "CLOTH_DOFFING": "Cloth doffing",
        "MANUAL_STOP": "Manual",
        "POWER_OFF": "Power off",
        "OTHER_STOP": "Other",
        "CC_BACK": "CC Back",
    },
    "pt": {
        "WARP_TOP_MISS": "Urdume(Superior)",
        "WARP_MISS": "Urdume",
        "FALSE_SELVAGE_MISS": "Ourela Falsa",
        "LENO_L_MISS": "Giro(Esq)",
        "LENO_R_MISS": "Giro(Dir)",
        "WEFT_MISS": "Trama",
        "WARP_OUT": "Troca de rolo de urdume",
        "CLOTH_DOFFING": "Troca de rolo de tecido",
        "MANUAL_STOP": "Manual",
        "POWER_OFF": "Desligada",
        "OTHER_STOP": "Outro",
        "CC_BACK": "Ourela Falsa(Atras)",
    },
}

# Layout dos códigos crus (índice no array bruto do tear → significado).
#
# JAT — 40 códigos:
#   0..4      Warp miss, False selvage, Leno(R), Leno(L), Manual check
#   5..10     WF1 color 1..6
#   11..16    WF2 color 1..6
#   17        Warp top miss
#   18..23    LH color 1..6
#   24        Warp out
#   25        Cloth doffing
#   26..38    Other (13)
#   39        Power off
#
# LWT — 31 códigos:
#   0..5      Warp miss, False selvage, CC Back, Leno(R), Leno(L), Manual
#   6..9      WF1 color 1..4
#   10        Warp top miss
#   11..14    LH color 1..4
#   15..19    Warp out, Cloth doffing, Other x3
#   20..23    WF2 color 1..4
#   24..29    Other x6
#   30        Power off

_N_COLORS_JAT = 6
_N_COLORS_LWT = 4


def _sum(values: Sequence[int]) -> int:
    return sum(values)


def get_detail_stop_jat(all_raw: Sequence[int]) -> Dict[str, List[int]]:
    """Agrega os 40 códigos brutos JAT nas 12 categorias + WF1/WF2/LH.

    Tem disfunções iguais às do legado: o retorno de CC Back é sempre 0 no JAT.
    """
    stop_ct = [0] * N_CATEGORIES
    stop_ct[0] = all_raw[17]                                   # Warp(Top)
    stop_ct[1] = all_raw[0]                                    # Warp
    stop_ct[2] = all_raw[1]                                    # False selvage
    stop_ct[3] = all_raw[3]                                    # Leno(L)
    stop_ct[4] = all_raw[2]                                    # Leno(R)
    stop_ct[5] = _sum(all_raw[5:17]) + _sum(all_raw[18:24])    # Weft
    stop_ct[6] = all_raw[24]                                   # Warp out
    stop_ct[7] = all_raw[25]                                   # Cloth doffing
    stop_ct[8] = all_raw[4]                                    # Manual
    stop_ct[9] = all_raw[39]                                   # Power off
    stop_ct[10] = _sum(all_raw[26:39])                         # Other
    stop_ct[11] = 0                                            # CC Back

    wf1 = [all_raw[5 + i] for i in range(_N_COLORS_JAT)]
    wf2 = [all_raw[11 + i] for i in range(_N_COLORS_JAT)]
    lh = [all_raw[18 + i] for i in range(_N_COLORS_JAT)]
    return {"stop_ct": stop_ct, "wf1": wf1, "wf2": wf2, "lh": lh}


def get_detail_stop_lwt(all_raw: Sequence[int]) -> Dict[str, List[int]]:
    """Agrega os 31 códigos brutos LWT nas 12 categorias + WF1/WF2/LH."""
    stop_ct = [0] * N_CATEGORIES
    stop_ct[0] = all_raw[10]                                   # Warp(Top)
    stop_ct[1] = all_raw[0]                                    # Warp
    stop_ct[2] = all_raw[1]                                    # False selvage
    stop_ct[3] = all_raw[4]                                    # Leno(L)
    stop_ct[4] = all_raw[3]                                    # Leno(R)
    stop_ct[5] = _sum(all_raw[6:10]) + _sum(all_raw[11:15]) + _sum(all_raw[20:24])
    stop_ct[6] = all_raw[15]                                   # Warp out
    stop_ct[7] = all_raw[16]                                   # Cloth doffing
    stop_ct[8] = all_raw[5]                                    # Manual
    stop_ct[9] = all_raw[30]                                   # Power off
    stop_ct[10] = _sum(all_raw[17:20]) + _sum(all_raw[24:30])  # Other
    stop_ct[11] = all_raw[2]                                   # CC Back

    wf1 = [all_raw[6 + i] for i in range(_N_COLORS_LWT)]
    wf2 = [all_raw[20 + i] for i in range(_N_COLORS_LWT)]
    lh = [all_raw[11 + i] for i in range(_N_COLORS_LWT)]
    return {"stop_ct": stop_ct, "wf1": wf1, "wf2": wf2, "lh": lh}


def get_detail_stop(mac_type: str, all_raw: Sequence[int]) -> Dict[str, List[int]]:
    if mac_type.upper() == LWT:
        return get_detail_stop_lwt(all_raw)
    return get_detail_stop_jat(all_raw)


def n_colors(mac_type: str) -> int:
    return _N_COLORS_LWT if mac_type.upper() == LWT else _N_COLORS_JAT


# Rótulo de parada cru → texto (get_stop_cause). Subconjunto documentado;
# a lista completa (~400 JAT / ~300 LWT) vive nos str_*.pm legados.
_RAW_JAT: Dict[str, str] = {
    "0000": "WARP STOP",
    "0001": "WASTE-SELVAGE STOP",
    "0002": "FULL-LENO SELVAGE STOP, RIGHT-HAND",
    "0003": "FULL-LENO SELVAGE STOP, LEFT-HAND",
}
for _i, _c in enumerate(range(4, 10), start=1):
    _RAW_JAT[f"{_c:04d}"] = f"WEFT STOP BY WF1 (COLOR {_i})"
for _i, _c in enumerate(range(10, 16), start=1):
    _RAW_JAT[f"{_c:04d}"] = f"WEFT STOP BY WF2 (COLOR {_i})"
for _i, _c in enumerate(range(16, 22), start=1):
    _RAW_JAT[f"{_c:04d}"] = f"WEFT SUPPLY STOP BY LH FEELER (COLOR {_i})"
_RAW_JAT.update({
    "0025": "CLOTH BEAM TO BE DOFFED",
    "0027": "[STOP] SWITCH PRESSED",
    "0028": "EMERGENCY STOP BUTTON PRESSED",
    "1502": "TAPO:INOPERABLE (NO MISSED WEFT)",
    "1503": "TAPO:PROCESSING FAILURE (TOO SHORT MISSED WEFT)",
    "1504": "TAPO:PROCESSING FAILURE (TOO LONG MISSED WEFT)",
    "2101": "REMOTE CONTROL STOP",
    "2150": "DECLARE(M/C TROUBLE)",
    "2151": "DECLARE(MENDING)",
    "2153": "DECLARE(WARP OUT)",
    "2154": "DECLARE(CLOTH DOFFING)",
    "2155": "DECLARE(FOREMAN CALL ON)",
    "2414": "WARP STOP (GROUND)",
    "2415": "WARP STOP (PILE)",
    "2420": "CLOTH BEAM TO BE DOFFED(COUNTER STOP)",
    "2421": "CLOTH BEAM TO BE DOFFED(FRINGE STOP)",
    "2422": "CLOTH BEAM TO BE DOFFED(CUTTING STOP)",
    "2430": "STOP LOT NUMBER",
    "2452": "MAIN CONTROL: COMMUNICATIONS ERROR WITH PILE LETOFF",
    "2470": "MAIN CONTROL: TUCKER BELT BREAK",
})

_RAW_LWT: Dict[str, str] = {
    "0000": "WARP STOP",
    "0001": "WASTE-SELVAGE STOP (FRONT)",
    "0002": "WASTE-SELVAGE STOP (REAR)",
    "0003": "FULL-LENO SELVAGE STOP (RIGHT-HAND)",
    "0004": "FULL-LENO SELVAGE STOP (LEFT-HAND)",
    "0005": "WEFT STOP (COLOR 1)",
    "0006": "WEFT STOP (COLOR 2)",
    "0007": "WEFT STOP (COLOR 3)",
    "0008": "WEFT STOP (COLOR 4)",
    "0009": "WEFT SUPPLY STOP (COLOR 1)",
    "0010": "WEFT SUPPLY STOP (COLOR 2)",
    "0011": "WEFT SUPPLY STOP (COLOR 3)",
    "0012": "WEFT SUPPLY STOP (COLOR 4)",
    "0013": "CLOTH BEAM TO BE DOFFED",
    "0014": "[STOP] SWITCH PRESSED",
    "0015": "EMERGENCY STOP BUTTON PRESSED",
    "2100": "REMOTE CONTROL LOCK",
    "2150": "DECLARE(M/C TROUBLE)",
    "2151": "DECLARE(MENDING)",
    "2153": "DECLARE(WARP OUT)",
    "2154": "DECLARE(CLOTH DOFFING)",
    "2155": "DECLARE(FOREMAN CALL ON)",
}

_RAW_BY_TYPE: Dict[str, Dict[str, str]] = {"JAT": _RAW_JAT, "LWT": _RAW_LWT}


def get_stop_cause(code: str, mac_type: str = "JAT", lang: str = "en") -> str:
    """Retorna o texto do código de parada (fallback: chave, como no legado)."""
    label = _RAW_BY_TYPE.get(mac_type.upper(), _RAW_JAT).get(code)
    if label is None:
        label = _RAW_JAT.get(code)
    if label is None:
        label = code
    return label