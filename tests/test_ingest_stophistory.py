from datetime import datetime, time
from pathlib import Path

from tms.ingest import parse_stophistory_file

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_stophistory_file():
    text = (FIXTURES / "stop_history_00000001.txt").read_text(encoding="utf-8")
    result = parse_stophistory_file(text)

    assert result.fixed is False
    assert result.day == "2026.07.01"
    assert result.day_date == datetime(2026, 7, 1)
    assert result.ip_addr == "172.17.1.1"
    assert result.mac_name == "00001"
    assert result.mac_type == "JAT710"
    assert len(result.events) == 4

    stopped = result.events[0]
    assert stopped.stop_time == time(6, 36, 9)
    assert stopped.run_time is None
    assert stopped.code == "2153"
    assert stopped.is_running is False

    running = result.events[1]
    assert running.stop_time is None
    assert running.run_time == time(10, 8, 59)
    assert running.code == "0027"
    assert running.is_running is True

    both = result.events[2]
    assert both.stop_time == time(10, 9, 11)
    assert both.run_time == time(10, 13, 1)
    assert both.code == "0000"
