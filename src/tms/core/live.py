"""Parser dos dados ao vivo do tear (`ext.cgi?func=get_stat` / scanner).

O legado (`loom/apistate.cgi::make_status_data`) recebe linhas ``Chave=valor``
do tear, valida a quantidade de campos e deriva o estado pelos bits. Esta
camada reproduz fielmente essa lógica (mesma ordem de precedência e mesmos
limites de completude), devolvendo um :class:`LiveStatus` puro — sem I/O.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

from tms.core.state import OFFLINE, RUN, STOPPED, NO_DATA, state_from_bits

# --- códigos de erro do legado (httpc.exe / opestate.cgi) -------------------

PING_TIMEOUT = 100
ARG_ERROR = 200
BAD_HOST_NAME = 201
POST_FILE_ERROR = 210
HTTP_NOT_FOUND = 220
HTTP_ERROR = 300
SOCKET_ERROR = 400
PING_ERROR = 410
SYSTEM_ERROR = 900
NOT_SUPPORT = 1000
DATA_ERROR = 1001

# Valores de completude (apistate.cgi:576-583)
JAT710_MIN_STATE = 14
LWT710_MIN_STATE = 15
MIN_DATA = 13
MIN_SET = 2

# Bits de estado na ordem de precedência do legado (último que casar vence).
BIT_PRECEDENCE = (
    ("manual", "Manual"),
    ("weft", "Weft"),
    ("leno_r", "Leno_R"),
    ("leno_l", "Leno_L"),
    ("catchcode_rear", "CatchCode_rear"),
    ("catchcode_front", "CatchCode_front"),
    ("false_selvage", "False_selvage"),
    ("warp", "Warp"),
    ("warp_top", "Warp_top"),
    ("power_off", "Power_off"),
    ("cloth_mending", "Cloth_mending"),
    ("machine_failure", "Machine_failure"),
    ("cloth_doffing", "Cloth_doffing"),
    ("warp_out", "Warp_out"),
    ("out_of_product", "Out_of_product"),
)

# chave do payload -> atributo do bits
STATE_KEYS = {
    "Stop": "stop",
    "Warp_top": "warp_top",
    "Warp": "warp",
    "False_selvage": "false_selvage",
    "CatchCode_front": "catchcode_front",
    "CatchCode_rear": "catchcode_rear",
    "Leno_L": "leno_l",
    "Leno_R": "leno_r",
    "Weft": "weft",
    "Manual": "manual",
    "Out_of_product": "out_of_product",
    "Warp_out": "warp_out",
    "Cloth_doffing": "cloth_doffing",
    "Cloth_mending": "cloth_mending",
    "Machine_failure": "machine_failure",
    "Power_off": "power_off",
}

DATA_KEYS = {
    "Rpm": "rpm",
    "Shift_efficiency": "effic_shift",
    "24h_efficiency": "effic_24h",
    "Shift_stops": "stop_shift",
    "24h_stops": "stop_24h",
    "Stop_time": "stop_time",
    "Run_time": "run_time",
    "Cloth_change_forecast": "doff_percent",
    "Cloth_change_time": "doff_forecast",
    "Beam_out_forecast": "wout_percent",
    "Beam_out_time": "wout_forecast",
    "Top_beam_out_forecast": "uwout_percent",
    "Top_beam_out_time": "uwout_forecast",
}

SET_KEYS = {
    "Style_name": "style",
    "Top_beam_use": "top_beam_use",
}

_ERROR_STATUS = {
    PING_TIMEOUT: "Power_off",
    PING_ERROR: "Comm_error",
    SOCKET_ERROR: "Comm_error",
    HTTP_ERROR: "Comm_error",
    HTTP_NOT_FOUND: "Comm_error",
    NOT_SUPPORT: "Not_support",
    DATA_ERROR: "Data_error",
}


def _to_float(value: str) -> Optional[float]:
    try:
        return float(value.strip())
    except (TypeError, ValueError):
        return None


def _to_int(value: str) -> int:
    number = _to_float(value)
    return int(number) if number is not None else 0


@dataclass
class LiveStatus:
    """Bits + dados + configuração reportados pelo tear (ou um erro de coleta)."""

    mac_type: str = "JAT710"
    bits: Dict[str, int] = field(default_factory=dict)
    data: Dict[str, Optional[float]] = field(default_factory=dict)
    setup: Dict[str, str] = field(default_factory=dict)
    scnt: int = 0
    dcnt: int = 0
    vcnt: int = 0
    error: Optional[int] = None

    # -- completude -------------------------------------------------------
    @property
    def required_state(self) -> int:
        return LWT710_MIN_STATE if self.mac_type == "LWT710" else JAT710_MIN_STATE

    @property
    def complete(self) -> bool:
        return (
            self.error is None
            and self.scnt >= self.required_state
            and self.dcnt >= MIN_DATA
            and self.vcnt >= MIN_SET
        )

    # -- conveniências ----------------------------------------------------
    @property
    def stop(self) -> int:
        return self.bits.get("stop", 0)

    @property
    def style(self) -> str:
        value = self.setup.get("style", "")
        return value.strip().strip('"')

    @property
    def top_beam_use(self) -> int:
        return _to_int(self.setup.get("top_beam_use", "0"))

    def value(self, name: str) -> Optional[float]:
        return self.data.get(name)

    @property
    def status(self) -> str:
        """Rótulo de estado do legado (Run / Manual / Weft / … / erro)."""
        if self.error is not None:
            return _ERROR_STATUS.get(self.error, "System_error")
        if self.stop == 0:
            return "Run"
        state = "Other"
        for bit, name in BIT_PRECEDENCE:
            if self.bits.get(bit):
                state = name
        return state

    @property
    def duration(self) -> Optional[float]:
        return self.data.get("stop_time" if self.stop == 1 else "run_time")

    @property
    def effic_shift(self) -> Optional[float]:
        value = self.data.get("effic_shift")
        return 100.0 if value is not None and value >= 100 else value

    @property
    def effic_24h(self) -> Optional[float]:
        value = self.data.get("effic_24h")
        return 100.0 if value is not None and value >= 100 else value


def error_status(code: int) -> LiveStatus:
    """Equivalente a `make_error_status` (todos os bits zerados)."""
    return LiveStatus(bits={name: 0 for name in STATE_KEYS.values()}, error=code)


def parse_live(
    lines: Sequence[str],
    *,
    validate: bool = True,
    error: Optional[int] = None,
) -> LiveStatus:
    """Converte as linhas ``Chave=valor`` em :class:`LiveStatus`."""
    live = LiveStatus(bits={name: 0 for name in STATE_KEYS.values()})

    for raw in lines:
        line = raw.rstrip("\r\n")
        if line.startswith("Machine_type=LWT710"):
            live.mac_type = "LWT710"
            continue
        key, _, value = line.partition("=")
        if not _:
            continue
        value = value.strip('"')
        if key in STATE_KEYS:
            live.bits[STATE_KEYS[key]] = _to_int(value)
            live.scnt += 1
        elif key in DATA_KEYS:
            live.data[DATA_KEYS[key]] = _to_float(value)
            live.dcnt += 1
        elif key in SET_KEYS:
            live.setup[SET_KEYS[key]] = value
            live.vcnt += 1

    if error is not None:
        live.error = error
    elif validate and not live.complete:
        live.error = DATA_ERROR
    return live


def live_to_monitor_state(live: LiveStatus) -> str:
    """Estado de monitor (run/stopped/offline/no_data) a partir do payload."""
    if live.error is not None:
        if live.error in (PING_TIMEOUT, ARG_ERROR, BAD_HOST_NAME, POST_FILE_ERROR):
            return OFFLINE
        if live.error in (HTTP_NOT_FOUND, NOT_SUPPORT, DATA_ERROR):
            return NO_DATA
        return OFFLINE
    state = state_from_bits(live.stop, live.bits)
    return RUN if state == RUN else STOPPED
