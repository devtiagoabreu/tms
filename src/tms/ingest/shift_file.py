"""Parser de `shift/<YYYY.MM.DD>.<n>.txt` — linha bruta diária por tear.

Formato (ver docs/migracao/02-modelo-de-dados.md §6):

```
fixed,mac_name 00001,mac_type JAT,ip_addr 172.17.1.1,shift 2025.10.01.0,
start 2025 10 1 3 5 20 0,style 2312,beam 123219,ubeam None,
seisan 2160 939 1027 0,off_prod 0 0 0 0,run_tm 23188,stop_ttm 6812,
s_ct <40>,s_tm <40>,tapo1..6 <6 cada>,tail1..6 <8 cada>
```

`run_tm`/`stop_ttm` em segundos inteiros. A agregação converte para minutos.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional

from tms.ingest._common import parse_int_list, parse_kv_line, parse_timestamp, to_int


@dataclass
class ShiftRecord:
    """Uma linha de `shift/<data>.<n>.txt` (tear × turno, valores crus)."""

    fixed: bool = False
    mac_name: str = ""
    mac_type: str = ""
    ip_addr: str = ""
    shift: str = ""
    start: Optional[datetime] = None
    style: str = ""
    beam: str = ""
    ubeam: str = ""
    seisan: List[int] = field(default_factory=list)
    off_prod: List[int] = field(default_factory=list)
    run_tm_sec: int = 0
    stop_ttm_sec: int = 0
    s_ct: List[int] = field(default_factory=list)
    s_tm: List[int] = field(default_factory=list)
    tapo: List[List[int]] = field(default_factory=list)
    tail: List[List[int]] = field(default_factory=list)

    @property
    def run_tm_min(self) -> float:
        return self.run_tm_sec / 60.0

    @property
    def stop_ttm_min(self) -> float:
        return self.stop_ttm_sec / 60.0


def parse_shift_line(line: str) -> Optional[ShiftRecord]:
    stripped = line.strip()
    if not stripped:
        return None
    # prefixo "fixed,"/"unfix," antes dos pares chave/valor
    fixed = stripped.startswith("fixed,")
    if stripped.startswith("fixed,") or stripped.startswith("unfix,"):
        stripped = stripped.split(",", 1)[1]
    kv = parse_kv_line(stripped)
    record = ShiftRecord(
        fixed=fixed,
        mac_name=kv.get("mac_name", ""),
        mac_type=kv.get("mac_type", ""),
        ip_addr=kv.get("ip_addr", ""),
        shift=kv.get("shift", ""),
        start=parse_timestamp(kv.get("start", "").split()),
        style=kv.get("style", ""),
        beam=kv.get("beam", ""),
        ubeam=kv.get("ubeam", ""),
        seisan=parse_int_list(kv.get("seisan", "")),
        off_prod=parse_int_list(kv.get("off_prod", "")),
        run_tm_sec=to_int(kv.get("run_tm", "")),
        stop_ttm_sec=to_int(kv.get("stop_ttm", "")),
        s_ct=parse_int_list(kv.get("s_ct", "")),
        s_tm=parse_int_list(kv.get("s_tm", "")),
    )
    record.tapo = [parse_int_list(kv.get(f"tapo{i}", "")) for i in range(1, 7)]
    record.tail = [parse_int_list(kv.get(f"tail{i}", "")) for i in range(1, 7)]
    return record


def parse_shift_file(text: str) -> List[ShiftRecord]:
    records = []
    for line in text.splitlines():
        record = parse_shift_line(line)
        if record is not None:
            records.append(record)
    return records
