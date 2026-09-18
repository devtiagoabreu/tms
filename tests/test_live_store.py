from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import tms.models  # noqa: F401  (registra as tabelas no metadata)
from tms.core.live import parse_live
from tms.db.base import Base
from tms.live_store import (
    latest_live,
    latest_live_by_name,
    latest_live_rows,
    persist_live,
    record_to_live,
)
from tms.models.masters import Machine

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    session.add_all(
        [
            Machine(mac_name="00001", mac_type="JAT", ip_addr="10.0.0.1"),
            Machine(mac_name="00002", mac_type="LWT", ip_addr="10.0.0.2"),
        ]
    )
    session.commit()
    try:
        yield session
    finally:
        session.close()


def _live(name: str):
    text = (FIXTURES / name).read_text(encoding="utf-8")
    return parse_live(text.splitlines())


def test_persist_and_latest(db):
    ids = {m.mac_name: m.id for m in db.query(Machine).all()}
    first = datetime(2026, 9, 17, 10, 0, 0)
    second = datetime(2026, 9, 17, 11, 0, 0)

    assert persist_live(db, ids, {"00001": _live("live_jat710.txt")}, collected_at=first) == 1
    assert persist_live(db, ids, {"00001": _live("live_lwt710.txt")}, collected_at=second) == 1
    assert persist_live(db, ids, {"ghost": _live("live_jat710.txt")}) == 0
    db.commit()

    latest = latest_live(db)
    assert set(latest) == {ids["00001"]}
    record = latest[ids["00001"]]
    assert record.collected_at == second
    assert record.status == "CatchCode_front"
    assert record.state == "stopped"
    assert record.mac_type == "LWT710"
    assert record.complete is True
    assert record.efficiency == 91.0

    rebuilt = record_to_live(record)
    assert rebuilt.status == "CatchCode_front"
    assert rebuilt.value("rpm") == 612

    by_name = latest_live_by_name(db)
    assert set(by_name) == {"00001"}

    rows = latest_live_rows(db)
    assert [name for name, _ in rows] == ["00001"]
