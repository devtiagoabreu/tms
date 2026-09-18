from tms.reporting.periods import (
    AggRecord,
    RawRecord,
    aggregate_agg_records,
    aggregate_records,
    month_key,
    period_key,
    week_key,
)

import pytest


def _raw(day, seisan_0=0, run=0, stop=0, s_ct0=0, s_tm0=0, mac="00001", mac_type="JAT"):
    size = 40 if mac_type == "JAT" else 31
    s_ct = [0] * size
    s_tm = [0] * size
    s_ct[0] = s_ct0
    s_tm[0] = s_tm0
    return RawRecord(
        mac_name=mac,
        mac_type=mac_type,
        style="2312",
        beam="123219",
        ubeam=None,
        seisan=(seisan_0, 500, 0, 0),
        off_prod=(100, 0, 0, 0),
        run_tm=run,
        stop_ttm=stop,
        s_ct=tuple(s_ct),
        s_tm=tuple(s_tm),
        day=day,
    )


def test_month_and_week_keys():
    assert month_key("2025.10.01") == "2025.10"
    # 2025.10.01 é quarta; semana domingo→domingo começa em 28/09
    assert week_key("2025.10.01", week_start=0) == "2025.09.28"
    assert week_key("2025.10.01", week_start=1) == "2025.09.29"
    assert period_key("day", "2025.10.01") == "2025.10.01"
    assert period_key("month", "2025.10.01") == "2025.10"
    assert period_key("shift", "2025.10.01.0") == "2025.10.01.0"


def _shift(day, shift_id, seisan_0=0, run=0, stop=0, mac="00001", mac_type="JAT"):
    s_ct = [0] * 12
    s_ct[1] = 2
    return AggRecord(
        mac_name=mac,
        mac_type=mac_type,
        style="2312",
        beam="123219",
        ubeam=None,
        seisan=(seisan_0, 0.0, 0.0),
        off_prod=(0.0, 0.0, 0.0),
        run_tm=seisan_0 / 1000 * 3 / 100,  # valor qualquer; só importa ser > 0 p/ filtro
        stop_ttm=0.0,
        stop_ct=tuple(s_ct),
        stop_tm=tuple(0.0 for _ in s_ct),
        day=day,
        shift_id=shift_id,
    )


def test_aggregate_shift_groups_by_shift_id():
    records = [
        _shift("2025.10.01", "2025.10.01.0", seisan_0=1000),
        _shift("2025.10.01", "2025.10.01.1", seisan_0=500),
    ]
    rows = aggregate_agg_records(records, "shift")
    assert len(rows) == 2
    keys = {r.key for r in rows}
    assert keys == {"2025.10.01.0", "2025.10.01.1"}
    # o mesmo shift_id soma dentro do próprio turno
    rows2 = aggregate_agg_records([records[0], records[0]], "shift")
    assert len(rows2) == 1
    assert rows2[0].key == "2025.10.01.0"


def test_aggregate_agg_operator_groups_by_operator():
    from dataclasses import replace

    base = _shift("2025.10.01", "2025.10.01.0", seisan_0=1000)
    a1 = replace(base)
    a2 = replace(base, operator_name="B")
    rows = aggregate_agg_records([a1, a2], "day", group_by="operator")
    assert len(rows) == 2
    assert {r.operator for r in rows} == {None, "B"}
    rows2 = aggregate_agg_records([a1, a1], "day", group_by="operator")
    assert len(rows2) == 1


def test_aggregate_agg_style_groups_by_style():
    from dataclasses import replace

    base = _shift("2025.10.01", "2025.10.01.0", seisan_0=1000)
    other = replace(base, mac_name="00002", style="1820")
    rows = aggregate_agg_records([base, other], "day", group_by="style")
    assert len(rows) == 2
    assert {r.style for r in rows} == {"2312", "1820"}
    assert {r.loom_count for r in rows} == {1}
    # dois teares do mesmo estilo somam e contam looms distintos
    same_style = replace(base, mac_name="00002")
    rows2 = aggregate_agg_records([base, same_style, same_style], "day", group_by="style")
    assert len(rows2) == 1
    assert rows2[0].style == "2312"
    assert rows2[0].loom_count == 2
    assert rows2[0].seisan[0] == 3000.0


def test_aggregate_style_none_style_uses_empty():
    from dataclasses import replace

    base = replace(_shift("2025.10.01", "2025.10.01.0", seisan_0=1000), style=None)
    rows = aggregate_agg_records([base, base], "day", group_by="style")
    assert len(rows) == 1
    assert rows[0].style is None
    assert rows[0].loom_count == 1


def test_aggregate_day_sums_and_recomputes():
    records = [
        _raw("2025.10.01", seisan_0=1000, run=3600, stop=3600, s_ct0=2, s_tm0=120),
        _raw("2025.10.02", seisan_0=500, run=1800, stop=0, s_ct0=0, s_tm0=0),
    ]
    rows = {r.key: r for r in aggregate_records(records, "day")}
    assert set(rows) == {"2025.10.01", "2025.10.02"}

    d1 = rows["2025.10.01"]
    assert d1.seisan[0] == 100.0
    assert d1.off_prod[0] == 10.0
    assert d1.run_tm == 60.0
    assert d1.stop_ttm == 60.0
    assert d1.effic == 50.0
    assert d1.rpm == pytest.approx(1000 * 100.0 / 60.0)
    assert d1.stop_ct[1] == 2
    assert d1.stop_tm[1] == 2.0
    assert d1.production() == 110.0


def test_aggregate_month_combines_records():
    records = [
        _raw("2025.10.01", seisan_0=1000, run=3600, stop=3600, s_ct0=2, s_tm0=120),
        _raw("2025.10.02", seisan_0=500, run=1800, stop=0),
    ]
    rows = aggregate_records(records, "month")
    assert len(rows) == 1
    row = rows[0]
    assert row.key == "2025.10"
    assert row.seisan[0] == 150.0
    assert row.run_tm == 90.0
    assert row.stop_ttm == 60.0
    assert row.effic == 60.0
    assert row.rpm == pytest.approx(1000 * 150.0 / 90.0)
    assert row.stop_ct[1] == 2
    assert row.stop_tm[1] == 2.0


def test_aggregate_week_groups_dates():
    records = [_raw("2025.10.01"), _raw("2025.10.02"), _raw("2025.10.06")]
    rows = aggregate_records(records, "week", week_start=0)
    keys = {r.key for r in rows}
    assert "2025.09.28" in keys
    assert "2025.10.05" in keys


def test_aggregate_filters_by_min_run_and_effic():
    records = [
        _raw("2025.10.01", seisan_0=1000, run=3600, stop=3600),
        _raw("2025.10.01", seisan_0=500, run=1800, stop=0),
    ]
    # min_run_tm=40 → exclui o registro de 30 min
    rows = aggregate_records(records, "day", min_run_tm=40)
    assert len(rows) == 1
    assert rows[0].seisan[0] == 100.0

    # min_effic=75 → exclui o de 50%
    rows = aggregate_records(records, "day", min_effic=75)
    assert len(rows) == 1
    assert rows[0].seisan[0] == 50.0
