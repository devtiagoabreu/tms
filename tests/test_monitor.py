from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import tms.models  # noqa: F401  (registra as tabelas no metadata)
from tms.core.state import decide_state, state_from_bits
from tms.db.base import Base
from tms.ingest import pipeline
from tms.monitor import build_monitor

FIXTURES = Path(__file__).parent / "fixtures"


def _text(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    pipeline.ingest_current(session, _text("current.txt"))
    pipeline.ingest_shift(session, _text("shift_2025.10.01.0.txt"), "2025.10.01.0")
    pipeline.ingest_stophistory(session, _text("stop_history_00000001.txt"))
    pipeline.ingest_stophistory(session, _text("stop_history_open_00000002.txt"))
    session.commit()
    try:
        yield session
    finally:
        session.close()


def test_decide_state():
    seen = datetime(2026, 9, 17, 14, 0)
    assert decide_state(last_seen=None, now=seen) == "no_data"
    assert decide_state(last_seen=seen, now=seen) == "run"
    assert decide_state(last_seen=seen, now=seen, has_open_stop=True) == "stopped"
    later = datetime(2026, 9, 17, 16, 0)
    assert decide_state(last_seen=seen, now=later, offline_after_s=900) == "offline"


def test_state_from_bits():
    assert state_from_bits(0, {}) == "run"
    assert state_from_bits(1, {}) == "stopped"
    assert state_from_bits(1, {"warp": 1}) == "stopped"


def test_build_monitor_states(db):
    now = datetime(2026, 9, 17, 14, 0, 0)
    items = {m["mac_name"]: m for m in build_monitor(db, now=now, offline_after_s=900)}

    # 00001: último evento do stop_history está fechado → run
    assert items["00001"]["state"] == "run"
    assert items["00001"]["stop"] is None
    assert items["00001"]["age_min"] == pytest.approx(1.9, abs=0.1)

    # 00002: snapshot fresco + parada em aberto (última linha com run_time "-")
    assert items["00002"]["state"] == "stopped"
    assert items["00002"]["stop"]["raw_code"] == "0004"
    assert items["00002"]["stop"]["cause"].startswith("WEFT STOP")
    assert items["00002"]["stop"]["duration_min"] > 0

    # 00005: existe no shift, mas sem snapshot → sem dados
    assert items["00005"]["state"] == "no_data"

    # production/effic vêm do último agg_shift
    assert items["00001"]["production"] is not None
    assert items["00001"]["efficiency"] is not None


def test_build_monitor_offline(db):
    now = datetime(2026, 9, 18, 14, 0, 0)
    items = {m["mac_name"]: m for m in build_monitor(db, now=now, offline_after_s=900)}
    assert items["00001"]["state"] == "offline"
    assert items["00002"]["state"] == "offline"


def test_build_monitor_live_overlay(db):
    from tms.core.live import parse_live

    live = parse_live(_text("live_jat710.txt").splitlines())
    now = datetime(2026, 9, 18, 14, 0, 0)  # offline pelo banco
    items = {
        m["mac_name"]: m
        for m in build_monitor(db, now=now, offline_after_s=900, live={"00002": live})
    }

    # estado ao vivo sobrepõe o "offline" calculado do banco
    assert items["00002"]["state"] == "stopped"
    assert items["00002"]["source"] == "live"
    assert items["00002"]["live"]["status"] == "Weft"
    assert items["00002"]["efficiency"] == 82.5
    assert items["00002"]["rpm"] == 558
    assert items["00002"]["style"] == "2312"

    # sem payload ao vivo, mantém a fonte do banco
    assert items["00001"]["source"] == "db"
    assert items["00001"]["live"] is None
