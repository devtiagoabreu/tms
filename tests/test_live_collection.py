"""Testes do coletor contínuo que alimenta ``live_status``."""

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

import tms.models  # noqa: F401  (registra as tabelas no metadata)
from tms.core.live import LiveStatus, error_status
from tms.db.base import Base
from tms.models.masters import Machine
from tms.models.runtime import LiveStatusRecord
from tms.services import live_collection


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    session.add_all(
        [
            Machine(mac_name="00001", mac_type="JAT", ip_addr="10.0.0.1"),
            Machine(mac_name="00002", mac_type="JAT", ip_addr="10.0.0.2"),
            Machine(mac_name="00003", mac_type="LWT", ip_addr=None),
        ]
    )
    session.commit()
    try:
        yield session
    finally:
        session.close()


def _live(rpm=500.0):
    return LiveStatus(
        mac_type="JAT710",
        bits={},
        data={"rpm": rpm, "effic_shift": 88.0, "run_time": 900.0, "stop_time": 60.0},
        setup={"style": "1210"},
        scnt=5,
        dcnt=13,
        vcnt=2,
    )


def test_collect_live_once_persists_every_loom(db, monkeypatch):
    seen = []

    def fake_fetch(ip, timeout=0):
        seen.append((ip, timeout))
        if ip == "10.0.0.2":
            return error_status(100)
        return _live()

    monkeypatch.setattr(live_collection, "fetch_live", fake_fetch)

    count = live_collection.collect_live_once(db, timeout=3.0, max_workers=2)

    assert count == 2
    assert set(seen) == {("10.0.0.1", 3.0), ("10.0.0.2", 3.0)}

    rows = db.execute(select(LiveStatusRecord)).scalars().all()
    assert len(rows) == 2
    by_machine = {row.machine_id: row for row in rows}
    assert by_machine[1].status == "Run"
    assert by_machine[1].rpm == pytest.approx(500.0)
    assert by_machine[1].error is None
    assert by_machine[2].error == 100


def test_collect_live_once_without_machines(db, monkeypatch):
    db.query(Machine).delete()
    db.commit()
    monkeypatch.setattr(
        live_collection, "fetch_live", lambda ip, timeout=0: pytest.fail("sem teares")
    )

    assert live_collection.collect_live_once(db) == 0
    assert db.query(LiveStatusRecord).count() == 0
