"""Testes do mapeamento de códigos de parada (40/31 → 12 categorias)."""

from tms.core.stopcodes import (
    CATEGORY_KEYS,
    get_detail_stop,
    get_detail_stop_jat,
    get_detail_stop_lwt,
)

JAT_EMPTY = [0] * 40
LWT_EMPTY = [0] * 31


def test_jat_has_40_categories():
    res = get_detail_stop_jat(JAT_EMPTY)
    assert len(res["stop_ct"]) == 12
    assert len(res["wf1"]) == 6
    assert len(res["wf2"]) == 6
    assert len(res["lh"]) == 6


def test_lwt_has_12_categories_and_4_colors():
    res = get_detail_stop_lwt(LWT_EMPTY)
    assert len(res["stop_ct"]) == 12
    assert len(res["wf1"]) == 4
    assert len(res["wf2"]) == 4
    assert len(res["lh"]) == 4


def test_jat_mapping_known_positions():
    raw = JAT_EMPTY[:]
    raw[17] = 10  # Warp top
    raw[0] = 11   # Warp
    raw[1] = 12   # False selvage
    raw[3] = 13   # Leno(L)
    raw[2] = 14   # Leno(R)
    raw[5] = 1    # WF1 c1
    raw[24] = 24  # Warp out
    res = get_detail_stop_jat(raw)
    assert res["stop_ct"][0] == 10
    assert res["stop_ct"][1] == 11
    assert res["stop_ct"][2] == 12
    assert res["stop_ct"][3] == 13
    assert res["stop_ct"][4] == 14
    assert res["stop_ct"][6] == 24
    assert res["stop_ct"][11] == 0  # CC Back sempre 0 no JAT
    assert res["wf1"][0] == 1


def test_jat_weft_sums_all_weft_sources():
    raw = JAT_EMPTY[:]
    for i in range(5, 17):
        raw[i] = 1
    for i in range(18, 24):
        raw[i] = 2
    res = get_detail_stop_jat(raw)
    assert res["stop_ct"][5] == 12 * 1 + 6 * 2


def test_jat_other_is_sum_26_38():
    raw = JAT_EMPTY[:]
    for i in range(26, 39):
        raw[i] = 3
    res = get_detail_stop_jat(raw)
    assert res["stop_ct"][10] == 13 * 3


def test_lwt_mapping_known_positions():
    raw = LWT_EMPTY[:]
    raw[10] = 20   # Warp top
    raw[0] = 21    # Warp
    raw[1] = 22    # False selvage
    raw[4] = 23    # Leno(L)
    raw[3] = 24    # Leno(R)
    raw[2] = 25    # CC Back
    raw[30] = 30   # Power off
    res = get_detail_stop_lwt(raw)
    assert res["stop_ct"][0] == 20
    assert res["stop_ct"][1] == 21
    assert res["stop_ct"][2] == 22
    assert res["stop_ct"][3] == 23
    assert res["stop_ct"][4] == 24
    assert res["stop_ct"][11] == 25
    assert res["stop_ct"][9] == 30


def test_lwt_weft_sums_all():
    raw = LWT_EMPTY[:]
    for i in range(6, 10):
        raw[i] = 1
    for i in range(11, 15):
        raw[i] = 2
    for i in range(20, 24):
        raw[i] = 3
    res = get_detail_stop_lwt(raw)
    assert res["stop_ct"][5] == 4 * 1 + 4 * 2 + 4 * 3


def test_dispatch_by_mac_type():
    assert get_detail_stop("LWT", LWT_EMPTY)["stop_ct"] == get_detail_stop_lwt(LWT_EMPTY)["stop_ct"]
    assert get_detail_stop("JAT", JAT_EMPTY)["stop_ct"] == get_detail_stop_jat(JAT_EMPTY)["stop_ct"]
    assert get_detail_stop("jat", JAT_EMPTY)["stop_ct"] == get_detail_stop_jat(JAT_EMPTY)["stop_ct"]


def test_category_keys_are_12():
    assert len(CATEGORY_KEYS) == 12