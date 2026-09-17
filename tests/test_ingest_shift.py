from datetime import datetime
from pathlib import Path

from tms.ingest import parse_shift_file, parse_shift_line

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_shift_file():
    text = (FIXTURES / "shift_2025.10.01.0.txt").read_text(encoding="utf-8")
    records = parse_shift_file(text)
    assert len(records) == 2

    first = records[0]
    assert first.fixed is True
    assert first.mac_name == "00001"
    assert first.mac_type == "JAT"
    assert first.shift == "2025.10.01.0"
    assert first.start == datetime(2025, 10, 1, 5, 20, 0)
    assert first.style == "2312"
    assert first.seisan == [2160, 939, 1027, 0]
    assert first.off_prod == [0, 0, 0, 0]
    assert first.run_tm_sec == 23188
    assert first.stop_ttm_sec == 6812
    assert first.run_tm_min == 23188 / 60.0
    assert len(first.s_ct) == 40
    assert len(first.s_tm) == 40
    assert len(first.tapo) == 6
    assert first.s_ct[5] == 1 and first.s_ct[6] == 9
    assert first.s_tm[6] == 6345

    second = records[1]
    assert second.fixed is False
    assert second.mac_name == "00005"
    assert second.mac_type == "LWT"


def test_parse_shift_line_minimal():
    record = parse_shift_line(
        "unfix,mac_name 00009,mac_type JAT,run_tm 60,stop_ttm 0,seisan 1 2 3 4"
    )
    assert record is not None
    assert record.fixed is False
    assert record.mac_name == "00009"
    assert record.seisan == [1, 2, 3, 4]
    assert record.s_ct == []
    assert parse_shift_line("") is None
