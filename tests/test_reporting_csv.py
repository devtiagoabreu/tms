import csv
import io

from tms.core.stopcodes import CATEGORY_KEYS
from tms.reporting.csv import header, write_csv
from tms.reporting.periods import aggregate_records
from test_reporting_periods import _raw


def _rows():
    records = [
        _raw("2025.10.01", seisan_0=1000, run=3600, stop=3600, s_ct0=2, s_tm0=120),
    ]
    return aggregate_records(records, "day")


def test_header_has_categories_and_totals():
    cols = header()
    assert cols[:7] == ["period", "key", "mac_name", "mac_type", "style", "beam", "ubeam"]
    assert cols[7:11] == ["rpm", "effic", "run_tm", "stop_ttm"]
    assert cols[11:19] == [
        "seisan_1", "seisan_2", "seisan_3",
        "off_prod_1", "off_prod_2", "off_prod_3",
        "production", "pick",
    ]
    assert [f"ct_{k}" for k in CATEGORY_KEYS] == cols[19:31]
    assert [f"tm_{k}" for k in CATEGORY_KEYS] == cols[31:43]
    assert cols[43:] == ["total_ct", "total2_ct", "wf1_ct", "wf1_tm", "wf2_ct", "wf2_tm", "lh_ct", "lh_tm"]


def test_write_csv_row_values():
    text = write_csv(_rows())
    lines = list(csv.reader(io.StringIO(text)))
    assert len(lines) == 2  # cabeçalho + 1 linha

    cols = lines[0]
    values = dict(zip(cols, lines[1]))
    assert values["mac_name"] == "00001"
    assert values["period"] == "day"
    assert values["key"] == "2025.10.01"
    assert values["seisan_1"] == "100.0"
    assert values["off_prod_1"] == "10.0"
    assert values["production"] == "110.0"
    assert values["run_tm"] == "60.000"
    assert values["effic"] == "50.00"
    # raw[0] → categoria WARP_MISS
    assert values["ct_WARP_MISS"] == "2"
    assert values["tm_WARP_MISS"] == "2.000"


def test_write_csv_uses_crlf():
    assert write_csv(_rows()).endswith("\r\n")
