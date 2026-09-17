"""Parser de `stop_history/<data>/<mac>.txt`.

Formato (ver docs/migracao/02-modelo-de-dados.md §4 e 04 §"Formatos"):

```
unfix,day 2026.07.01,ip_addr 172.17.1.1,mac_name 00001,mac_type JAT710
06:36:09,-,2153
-,10:08:59,0027
10:09:11,10:13:01,0000
```

Cada linha de evento é ``stop_time,run_time,code``; ``-`` indica ausente.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, time
from typing import List, Optional

from tms.ingest._common import parse_kv_line


@dataclass
class StopInterval:
    """Par `stop_time,run_time,code` de um evento."""

    stop_time: Optional[time]
    run_time: Optional[time]
    code: str

    @property
    def is_running(self) -> bool:
        """``run_time`` presente = segmento de rodagem (sem parada)."""
        return self.stop_time is None and self.run_time is not None


@dataclass
class StopHistoryFile:
    """Conteúdo de um arquivo de histórico de paradas do dia."""

    fixed: bool = False
    day: str = ""
    ip_addr: str = ""
    mac_name: str = ""
    mac_type: str = ""
    events: List[StopInterval] = field(default_factory=list)
    # dia (yyyy.mm.dd) para compor os timestamps absolutos
    day_date: Optional[datetime] = None


def _parse_time(token: str) -> Optional[time]:
    token = token.strip()
    if not token or token == "-":
        return None
    parts = token.split(":")
    if len(parts) != 3:
        return None
    try:
        return time(int(parts[0]), int(parts[1]), int(parts[2]))
    except ValueError:
        return None


def _parse_day(day: str) -> Optional[datetime]:
    try:
        return datetime.strptime(day, "%Y.%m.%d")
    except ValueError:
        return None


def parse_stophistory_file(text: str) -> StopHistoryFile:
    lines = text.splitlines()
    result = StopHistoryFile()
    if not lines:
        return result

    header = lines[0]
    result.fixed = header.startswith("fixed")
    kv = parse_kv_line(header)
    result.day = kv.get("day", "")
    result.ip_addr = kv.get("ip_addr", "")
    result.mac_name = kv.get("mac_name", "")
    result.mac_type = kv.get("mac_type", "")
    result.day_date = _parse_day(result.day)

    for line in lines[1:]:
        line = line.strip()
        if not line:
            continue
        parts = line.split(",")
        if len(parts) != 3:
            continue
        result.events.append(
            StopInterval(
                stop_time=_parse_time(parts[0]),
                run_time=_parse_time(parts[1]),
                code=parts[2].strip(),
            )
        )
    return result
