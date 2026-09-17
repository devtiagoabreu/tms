"""Estado do tear derivado dos dados ingeridos.

O legado (`loom/apistate.cgi::make_status_data`) deriva o estado de bits ao
vivo enviados pelo tear (Stop, Warp, Weft, …). Essa coleta em tempo real ainda
não foi migrada; aqui o estado é inferido de:

- frescura do último snapshot (`machine_snapshots.get_time`) → ``offline``;
- existência de parada em aberto em `stop_events` → ``stopped``;
- caso contrário → ``run``.

Quando a camada de coleta ao vivo existir, basta passar os bits para
:func:`state_from_bits`, mantendo a mesma precedência do legado.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Mapping, Optional

RUN = "run"
STOPPED = "stopped"
OFFLINE = "offline"
NO_DATA = "no_data"

STATES = (RUN, STOPPED, OFFLINE, NO_DATA)

STATE_LABELS = {
    RUN: {"en": "Running", "pt": "Em operação", "ja": "稼働中"},
    STOPPED: {"en": "Stopped", "pt": "Parada", "ja": "停止中"},
    OFFLINE: {"en": "Communication error", "pt": "Sem comunicação", "ja": "通信異常"},
    NO_DATA: {"en": "No data", "pt": "Sem dados", "ja": "データなし"},
}

# Cores inspiradas no dashboard legado (Run verde; parada vermelha).
STATE_COLORS = {
    RUN: "#4CAF50",
    STOPPED: "#F44336",
    OFFLINE: "#9E9E9E",
    NO_DATA: "#607D8B",
}

# Bits → estado, na ordem de precedência do legado (último vence).
_BIT_PRECEDENCE = (
    ("manual", STOPPED),
    ("weft", STOPPED),
    ("leno_r", STOPPED),
    ("leno_l", STOPPED),
    ("catchcode_rear", STOPPED),
    ("catchcode_front", STOPPED),
    ("false_selvage", STOPPED),
    ("warp", STOPPED),
    ("warp_top", STOPPED),
    ("power_off", STOPPED),
    ("cloth_mending", STOPPED),
    ("machine_failure", STOPPED),
    ("cloth_doffing", STOPPED),
    ("warp_out", STOPPED),
    ("out_of_product", STOPPED),
)


def state_from_bits(stop: Optional[int], bits: Mapping[str, object]) -> str:
    """Estado a partir dos bits ao vivo (precedência do apistate.cgi)."""
    if stop == 0:
        return RUN
    state = STOPPED
    for name, mapped in _BIT_PRECEDENCE:
        if bits.get(name):
            state = mapped
    return state


def decide_state(
    *,
    last_seen: Optional[datetime],
    now: datetime,
    offline_after_s: int = 900,
    has_open_stop: bool = False,
) -> str:
    """Infere o estado do tear pela frescura do snapshot + parada em aberto."""
    if last_seen is None:
        return NO_DATA
    if (now - last_seen).total_seconds() > offline_after_s:
        return OFFLINE
    if has_open_stop:
        return STOPPED
    return RUN


def is_fresh(last_seen: Optional[datetime], now: datetime, offline_after_s: int = 900) -> bool:
    return last_seen is not None and (now - last_seen) <= timedelta(seconds=offline_after_s)


def label(state: str, lang: str = "pt") -> str:
    table = STATE_LABELS.get(state, {})
    return table.get(lang) or table.get("en") or state


def color(state: str) -> str:
    return STATE_COLORS.get(state, STATE_COLORS[NO_DATA])
