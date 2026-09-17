"""Coleta e ingestão de dados das máquinas (Fase 1).

Parsers puros dos arquivos gerados pelo legado em `tmsdata/`:

- `loom_file`        — `loom/<mac>.txt` (registro diário por tear)
- `current_file`     — `current/current.txt` e `current/setting.txt` (snapshots)
- `shift_file`       — `shift/<YYYY.MM.DD>.<n>.txt` (linha bruta diária)
- `stophistory_file` — `stop_history/<data>/<mac>.txt` (histórico de paradas)
"""

from tms.ingest.current_file import (
    CurrentRecord,
    SettingRecord,
    parse_current_file,
    parse_current_line,
    parse_setting_file,
    parse_setting_line,
)
from tms.ingest.loom_file import LoomFile, MoniShift, parse_loom_file
from tms.ingest.shift_file import ShiftRecord, parse_shift_file, parse_shift_line
from tms.ingest.stophistory_file import (
    StopHistoryFile,
    StopInterval,
    parse_stophistory_file,
)

__all__ = [
    "CurrentRecord",
    "SettingRecord",
    "parse_current_file",
    "parse_current_line",
    "parse_setting_file",
    "parse_setting_line",
    "LoomFile",
    "MoniShift",
    "parse_loom_file",
    "ShiftRecord",
    "parse_shift_file",
    "parse_shift_line",
    "StopHistoryFile",
    "StopInterval",
    "parse_stophistory_file",
]
