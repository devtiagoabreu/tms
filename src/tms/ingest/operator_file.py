"""Parser de `operator/<YYYY.MM.DD>.txt` — produção por operador/dia.

Uma linha por (tear × operador), no mesmo formato `k v` separado por vírgulas
do `shift/`, com os campos `ope_num`/`ope_name` (ver
docs/migracao/02-modelo-de-dados.md §5).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional

from tms.ingest._common import parse_int_list, parse_kv_line, parse_timestamp, to_int


@dataclass
class OperatorRecord:
    """Linha de `operator/<data>.txt` (tear × operador × dia)."""

    fixed: bool = False
    mac_name: str = ""
    mac_type: str = ""
    ip_addr: str = ""
    day: str = ""
    start: Optional[datetime] = None
    ope_num: str = ""
    ope_name: str = ""
    style: str = ""
    beam: str = ""
    ubeam: str = ""
    seisan: List[int] = field(default_factory=list)
    run_tm_sec: int = 0
    stop_ttm_sec: int = 0
    s_ct: List[int] = field(default_factory=list)
    s_tm: List[int] = field(default_factory=list)

    @property
    def run_tm_min(self) -> float:
        return self.run_tm_sec / 60.0

    @property
    def stop_ttm_min(self) -> float:
        return self.stop_ttm_sec / 60.0


def parse_operator_line(line: str) -> Optional[OperatorRecord]:
    stripped = line.strip()
    if not stripped:
        return None
    fixed = stripped.startswith("fixed,")
    if stripped.startswith("fixed,") or stripped.startswith("unfix,"):
        stripped = stripped.split(",", 1)[1]
    kv = parse_kv_line(stripped)
    return OperatorRecord(
        fixed=fixed,
        mac_name=kv.get("mac_name", ""),
        mac_type=kv.get("mac_type", ""),
        ip_addr=kv.get("ip_addr", ""),
        day=kv.get("day", ""),
        start=parse_timestamp(kv.get("start", "").split()),
        ope_num=kv.get("ope_num", ""),
        ope_name=kv.get("ope_name", ""),
        style=kv.get("style", ""),
        beam=kv.get("beam", ""),
        ubeam=kv.get("ubeam", ""),
        seisan=parse_int_list(kv.get("seisan", "")),
        run_tm_sec=to_int(kv.get("run_tm", "")),
        stop_ttm_sec=to_int(kv.get("stop_ttm", "")),
        s_ct=parse_int_list(kv.get("s_ct", "")),
        s_tm=parse_int_list(kv.get("s_tm", "")),
    )


def parse_operator_file(text: str) -> List[OperatorRecord]:
    records = []
    for line in text.splitlines():
        record = parse_operator_line(line)
        if record is not None:
            records.append(record)
    return records
