"""Modelos ORM. Schema proposto em docs/migracao/07-plano-migracao-python.md §3."""

from tms.db.base import Base
from tms.models.masters import (
    IpRange,
    Machine,
    Operator,
    ReportPref,
    Setting,
    ShiftSchedule,
    Style,
)
from tms.models.runtime import (
    AggShift,
    DailyRaw,
    LiveStatusRecord,
    MachineSnapshot,
    OperatorDaily,
    StopEvent,
)

__all__ = [
    "AggShift",
    "Base",
    "DailyRaw",
    "IpRange",
    "LiveStatusRecord",
    "Machine",
    "MachineSnapshot",
    "Operator",
    "OperatorDaily",
    "ReportPref",
    "Setting",
    "ShiftSchedule",
    "StopEvent",
    "Style",
]