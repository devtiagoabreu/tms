from datetime import date

import pytest

from tms.ingest.loom_file import parse_loom_file
from tms.services.loom_history import day_production, day_stops

PAYLOAD = "\n".join(
    [
        "JAT710-TMS-DATA stop_history",
        "MH_t_tm 2026 11 5 4 6 0 0",
        "MH_t_h0_history 10:00:00 10:05:00 0004",
        "MH_d0_tm 2026 11 4 3 6 0 0",
        "MH_d0_h0_history 11:00:00 11:05:00 0000",
        "#end_of_data",
        "JAT700-MCARD-DATA moni_monitor",
        "PM_y3_p5_seisan 1 2 3 0",
        "PM_y3_pd_tm 2026 11 4 3 6 0 0",
        "MJ_s0_y3_seisan 100 80 90 0",
        "MJ_s0_y3_tm 2026 11 4 3 5 0 0",
        "MJ_s0_y3_rt 18000",
        "MJ_s0_y3_to 14400",
        "MJ_s1_y3_seisan 200 160 180 0",
        "MJ_s1_y3_tm 2026 11 4 3 14 0 0",
        "MJ_s1_y3_rt 20000",
        "MJ_s1_y3_to 14500",
        "#end_of_data",
    ]
)


def test_day_production_soma_turnos_mj():
    loom = parse_loom_file(PAYLOAD)

    production = day_production(loom, date(2026, 11, 4))

    assert production is not None
    # MJ_s0 + MJ_s1, dividido por 10 como no agg_shift do legado.
    assert production.picks == 30.0
    assert production.meters == 24.0
    assert production.yards == 27.0
    assert production.run_minutes == pytest.approx((18000 + 20000) / 60, abs=1e-3)
    assert production.stop_minutes == pytest.approx((14400 + 14500) / 60, abs=1e-3)


def test_day_production_usa_pm_quando_nao_ha_turnos():
    loom = parse_loom_file(
        "\n".join(
            [
                "JAT700-MCARD-DATA moni_monitor",
                "PM_y3_p5_seisan 300 250 270 0",
                "PM_y3_pd_tm 2026 11 4 3 6 0 0",
                "#end_of_data",
            ]
        )
    )

    production = day_production(loom, date(2026, 11, 4))

    assert production is not None
    assert production.picks == 30.0
    assert production.meters == 25.0


def test_day_stops_ignora_dia_corrente_e_usa_d0():
    loom = parse_loom_file(PAYLOAD)

    stops = day_stops(loom, date(2026, 11, 4), "JAT")

    assert stops is not None
    assert stops.total_count == 1
    assert stops.counts[1] == 1  # 0000 = WARP_MISS (urdume)
    assert stops.counts[5] == 0  # MH_t não pode vazar para o dia passado
