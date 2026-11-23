"""Modelos ORM."""

from tms.db.base import Base
from tms.models.auth import User, UserRole
from tms.models.daily import DailyCollectionItem, DailyCollectionRun, DailyLoomData
from tms.models.masters import (
    IpRange,
    Machine,
    Operator,
    ReportPref,
    Setting,
    ShiftSchedule,
    Style,
)
from tms.models.navigation import Menu, MenuItem
from tms.models.notification import Notification, NotificationRule
from tms.models.runtime import (
    AggShift,
    DailyRaw,
    LiveStatusRecord,
    MachineSnapshot,
    OperatorDaily,
    StopEvent,
)
from tms.models.collector_state import CollectorState
from tms.models.loom_command import LoomCommand
from tms.models.machine_group import MachineGroup, MachineGroupMember
from tms.models.permission import Permission, RolePermission
from tms.models.shift_turn import ShiftTurn
from tms.models.system_config import SystemConfig

__all__ = [
    "AggShift",
    "Base",
    "CollectorState",
    "DailyCollectionItem",
    "DailyCollectionRun",
    "DailyLoomData",
    "DailyRaw",
    "IpRange",
    "LiveStatusRecord",
    "LoomCommand",
    "Machine",
    "MachineGroup",
    "MachineGroupMember",
    "MachineSnapshot",
    "Permission",
    "RolePermission",
    "Menu",
    "MenuItem",
    "Notification",
    "NotificationRule",
    "Operator",
    "OperatorDaily",
    "ReportPref",
    "Setting",
    "ShiftSchedule",
    "ShiftTurn",
    "StopEvent",
    "Style",
    "SystemConfig",
    "User",
    "UserRole",
]

