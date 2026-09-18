import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import tms.models  # noqa: F401  (registra as tabelas no metadata)
from tms import config_service as cfg
from tms.db.base import Base

SELITEM = """Version 3.00
item2     0 0 1 1 1 1 1
item      0 1 0 1 1 1 0 0 0 0 0
item3     0 0 0
detail    1 0 0
color     1 1 0 0 0 0
beam_type 1
unit      0
period    shift
week      0
effic     090
run_tm    030
expire    26
"""


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()


def test_settings_crud(db):
    assert cfg.get_setting(db, "language", "en") == "en"
    cfg.set_setting(db, "language", "pt")
    assert cfg.get_setting(db, "language") == "pt"
    assert cfg.all_settings(db) == {"language": "pt"}
    cfg.set_setting(db, "language", None)
    assert cfg.get_setting(db, "language") is None


def test_ip_ranges_roundtrip(db):
    text = "172 17 1 1 16\n172 17 1 28 35\n172 17 1 42 43\n"
    ranges = cfg.parse_ip_ranges(text)
    assert ranges == [(172, 17, 1, 1, 16), (172, 17, 1, 28, 35), (172, 17, 1, 42, 43)]
    assert cfg.format_ip_ranges(ranges) == text
    assert len(cfg.expand_ip_ranges(ranges)) == 16 + 8 + 2


def test_ip_ranges_merge_and_validation():
    # 1..16 e 17..20 se tocam na mesma sub-rede → unem em 1..20
    merged = cfg.merge_ip_ranges([(172, 17, 1, 1, 16), (172, 17, 1, 17, 20)])
    assert merged == [(172, 17, 1, 1, 20)]
    # 4 tokens → faixa de 1 IP; start>end trocado; >255 descartado
    parsed = cfg.parse_ip_ranges("10 0 0 5\n10 0 1 9 3\n10 0 2 1 300\n")
    assert parsed == [(10, 0, 0, 5, 5), (10, 0, 1, 3, 9)]


def test_replace_ip_ranges(db):
    cfg.replace_ip_ranges(db, "172 17 1 1 16\n172 17 1 17 20\n")
    db.commit()
    assert cfg.get_ip_ranges(db) == [(172, 17, 1, 1, 20)]


def test_styles_roundtrip(db):
    text = "2312\t70\t100\nB100\t60\t120\n"
    styles = cfg.parse_styles(text)
    assert styles[0] == {"name": "2312", "density": "70", "doff_len": 100}
    assert cfg.format_styles(styles) == text

    cfg.replace_styles(db, text)
    db.commit()
    assert [s["name"] for s in cfg.get_styles(db)] == ["2312", "B100"]

    # remove ausentes e atualiza existentes
    cfg.replace_styles(db, "2312\t75\t110\n")
    db.commit()
    styles = cfg.get_styles(db)
    assert [s["name"] for s in styles] == ["2312"]
    assert styles[0]["density"] == "75"
    assert styles[0]["doff_len"] == 110


def test_shift_schedule_roundtrip(db):
    text = (
        "shift_schedule_is_week 0\n"
        "shift_schedule_simple 3 05:00 14:00 23:35 05:00 14:00 23:35\n"
    )
    schedule = cfg.parse_shift_schedule(text)
    assert schedule["is_week"] == 0
    assert schedule["simple"][0] == 3
    assert cfg.format_shift_schedule(schedule) == text

    cfg.replace_shift_schedule(db, text)
    db.commit()
    loaded = cfg.get_shift_schedule(db)
    assert loaded["simple"] == schedule["simple"]

    week = (
        "shift_schedule_is_week 1\n"
        "shift_schedule_simple 0\n"
        "shift_schedule_week 1 2 06:00 14:00 22:00 06:00\n"
    )
    cfg.replace_shift_schedule(db, week)
    db.commit()
    loaded = cfg.get_shift_schedule(db)
    assert loaded["is_week"] == 1
    assert loaded["week"]["1"][0] == 2


def test_report_prefs_roundtrip(db):
    prefs = cfg.parse_report_prefs(SELITEM)
    assert prefs["item2"] == [0, 0, 1, 1, 1, 1, 1]
    assert prefs["item"] == [0, 1, 0, 1, 1, 1, 0, 0, 0, 0, 0]
    assert prefs["color"] == [1, 1, 0, 0, 0, 0]
    assert prefs["effic"] == 90 and prefs["run_tm"] == 30 and prefs["expire"] == 26
    assert cfg.parse_report_prefs(cfg.format_report_prefs(prefs)) == prefs

    cfg.replace_report_prefs(db, prefs)
    db.commit()
    assert cfg.get_report_prefs(db) == prefs

    # defaults preenchem chaves ausentes
    cfg.replace_report_prefs(db, {"item2": [1, 1, 1, 1, 1, 1, 1]})
    db.commit()
    loaded = cfg.get_report_prefs(db)
    assert loaded["item2"] == [1] * 7
    assert loaded["item"] == cfg.SELITEM_DEFAULTS["item"]
