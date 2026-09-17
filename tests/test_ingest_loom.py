from datetime import datetime, time
from pathlib import Path

from tms.ingest import parse_loom_file

FIXTURES = Path(__file__).parent / "fixtures"


def _loom():
    text = (FIXTURES / "loom_00001.txt").read_text(encoding="utf-8")
    return parse_loom_file(text)


def test_header_and_current_section():
    loom = _loom()
    assert loom.get_time == datetime(2026, 9, 17, 13, 58, 9)
    assert loom.mac_name == "00001"
    assert loom.ip_addr == "172.17.1.1"
    assert loom.mac_type == "JAT710"
    assert loom.sys_time == datetime(2026, 9, 17, 14, 8, 5)
    assert loom.rtc_time == datetime(2026, 9, 17, 10, 8, 5)
    assert loom.clock_diff_seconds == 4 * 3600
    assert loom.shift == "1"
    assert loom.style == "1210"
    assert loom.beam == "123219"
    assert loom.s_beam == [90000, 98416]
    assert loom.cloth_len == [7626, 6355, 6950, 0]
    assert loom.wout_fcst == 18042


def test_stop_history_events():
    loom = _loom()
    assert len(loom.stop_events) == 3

    first = loom.stop_events[0]
    assert first.day == 0 and first.hour == 0
    assert first.start is None
    assert first.end == time(5, 6, 48)
    assert first.code == "0027"

    second = loom.stop_events[1]
    assert second.start == time(5, 10, 41)
    assert second.end == time(5, 13, 37)
    assert second.code == "0005"

    assert loom.day_start[0] == datetime(2026, 9, 16, 0, 0, 0)
    assert loom.day_start[1] == datetime(2026, 9, 17, 0, 0, 0)


def test_file_info_and_monitor():
    loom = _loom()
    assert loom.file_info["machine"] == "00001"
    assert loom.file_info["style"] == "1210"
    assert loom.file_info["top_beam"] == ""

    current = loom.current_shift
    assert current is not None
    assert current.seisan == [2394, 2082, 2276, 0]
    assert current.rt == 28272
    assert len(current.sc) == 40
    assert current.to == 4128
    assert current.tm == datetime(2026, 9, 17, 5, 0, 0)
    assert current.sn == "1210"

    assert loom.next_shift is not None
    assert loom.next_shift.rt == 0

    pick = loom.pick
    assert pick is not None
    assert pick.seisan == [2160, 939, 1027, 0]
    assert pick.ss == [95, 94, 93]
    assert pick.en == [90, 0, 0]
    assert loom.pick_now_p == 5


def test_shift_config():
    loom = _loom()
    assert loom.shift_mode == 0
    assert loom.simple == ["3", "05:00", "14:00", "23:35", "-1:-1", "-1:-1"]
    assert loom.days[0] == ["3", "06:14", "14:22", "22:06", "-1:-1", "-1:-1"]
    assert loom.days[1] == ["3", "05:14", "14:22", "22:06", "-1:-1", "-1:-1"]
    assert loom.days[6] == ["3", "06:14", "14:22", "22:06", "-1:-1", "-1:-1"]
    assert loom.names[0] == ""
    assert loom.names[1] == "Anderson"
    assert loom.day_start_time == "6:0"
