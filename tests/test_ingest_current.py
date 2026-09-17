from datetime import datetime
from pathlib import Path

from tms.ingest import parse_current_file, parse_setting_file

FIXTURES = Path(__file__).parent / "fixtures"


def _text(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_parse_current_file():
    records = parse_current_file(_text("current.txt"))
    assert len(records) == 2

    first = records[0]
    assert first.mac_name == "00001"
    assert first.mac_type == "JAT"
    assert first.ip_addr == "172.17.1.1"
    assert first.shift == "2026.09.17.1"
    assert first.get_time == datetime(2026, 9, 17, 13, 58, 9)
    assert first.sys_time == datetime(2026, 9, 17, 14, 8, 5)
    assert first.style == "1210"
    assert first.beam == "123219"
    assert first.s_beam == [90000, 98416]
    assert first.r_beam == [68606, 75021]
    assert first.cloth_len == [7626, 6355, 6950, 0]
    assert first.wout_fcst == 18042
    assert first.rtc_time is None

    second = records[1]
    assert second.mac_name == "00002"
    assert second.beam == "Undefined"
    assert second.r_beam == [-17500, -19137]


def test_parse_setting_file():
    records = parse_setting_file(_text("setting.txt"))
    assert len(records) == 1

    record = records[0]
    assert record.mac_name == "00001"
    assert record.rtc_time == datetime(2026, 9, 17, 10, 8, 5)
    assert record.shift_mode == 0
    assert record.simple == ["3", "05:00", "14:00", "23:35", "-1:-1", "-1:-1"]
    assert record.days[0] == ["3", "06:14", "14:22", "22:06", "-1:-1", "-1:-1"]
    assert record.days[1] == ["3", "05:14", "14:22", "22:06", "-1:-1", "-1:-1"]
    assert record.names[0] == "Undefined1"
    assert record.names[1] == "Anderson"
    assert record.day_start_time == "6:0"
    assert record.clock_diff_seconds == 4 * 3600
