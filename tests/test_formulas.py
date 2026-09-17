"""Testes das fórmulas canônicas dos relatórios."""

from tms.core.formulas import (
    effic,
    false_cc_total,
    leno_total,
    production,
    rpm,
    shiftreport_total,
    shiftreport_total2,
    svs_other,
    svs_pick,
    warp_ct,
    weft_ct,
)


def test_rpm():
    # RPM = seisan[0]*100 / (run_tm/60); run_tm em minutos
    assert abs(rpm(5, 6) - 5000.0) < 1e-9
    assert rpm(1000, 0) == 0.0


def test_effic():
    assert abs(effic(90, 10) - 90.0) < 1e-9
    assert effic(0, 0) == 0.0


def test_production():
    assert production([100, 50, 25], [10, 5, 0]) == 110
    assert production([100, 50, 25], [10, 5], 2) == 25  # off_prod ausente → 0
    assert production([100, 50, 25], []) == 100


def test_false_and_leno_totals():
    stop_ct = [0, 0, 7, 3, 4, 0, 0, 0, 0, 0, 0, 5]
    assert false_cc_total(stop_ct) == 12
    assert leno_total(stop_ct) == 7


def test_warp_and_weft_ct():
    stop_ct = [1, 2, 3, 4, 5, 6, 0, 0, 0, 0, 0, 7]
    assert warp_ct(stop_ct) == 1 + 2 + 3 + 4 + 5 + 7
    assert weft_ct(stop_ct) == 6


def test_shiftreport_totals_exclude_warp_top_when_beam_type_1():
    stop_ct = [10, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]
    assert shiftreport_total(stop_ct, beam_type=1) == sum(stop_ct) - 10
    assert shiftreport_total(stop_ct, beam_type=2) == sum(stop_ct)


def test_shiftreport_total2():
    stop_ct = [1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 1]
    # warp + weft + false(2+11) + leno(3+4)
    assert shiftreport_total2(stop_ct, beam_type=2) == 1 + 1 + 1 + 2 + 2
    assert shiftreport_total2(stop_ct, beam_type=1) == 1 + 1 + 1 + 2 + 2 - 1


def test_svs_pick():
    assert svs_pick(311.8) == 311800.0


def test_svs_other():
    stop_ct = [0, 0, 1, 2, 3, 0, 0, 0, 0, 0, 0, 4]
    assert svs_other(stop_ct, [1, 2]) == (1 + 2 + 3) + 4 + 3