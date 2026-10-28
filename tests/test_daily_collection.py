from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

import tms.models  # noqa: F401  (registra as tabelas no metadata)
from tms.core.live import LiveStatus, error_status
from tms.db.base import Base
from tms.models.daily import DailyCollectionItem, DailyCollectionRun, DailyLoomData
from tms.models.masters import Machine
from tms.models.runtime import AggShift, LiveStatusRecord
from tms.services import daily_collection

DAY = date(2026, 10, 27)


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


def _live(rpm=500.0, style="1210"):
    return LiveStatus(
        mac_type="JAT710",
        bits={},
        data={"rpm": rpm, "effic_shift": 88.0, "run_time": 900.0, "stop_time": 60.0, "stop_shift": 4},
        setup={"style": style},
        scnt=5,
        dcnt=13,
        vcnt=2,
    )


def _seed_history(db, machine_id: int):
    start = datetime.combine(DAY, datetime.min.time()) + timedelta(hours=8)
    db.add_all(
        [
            LiveStatusRecord(
                machine_id=machine_id,
                collected_at=start,
                state="run",
                status="Run",
                rpm=500.0,
                efficiency=90.0,
                bits={},
                data={"run_time": 900.0, "stop_time": 60.0, "stop_shift": 3},
                setup={"style": "1210"},
            ),
            LiveStatusRecord(
                machine_id=machine_id,
                collected_at=start + timedelta(minutes=1),
                state="stopped",
                status="Weft",
                rpm=490.0,
                efficiency=88.5,
                bits={"weft": 1},
                data={"run_time": 900.0, "stop_time": 61.0, "stop_shift": 4},
                setup={"style": "1210"},
            ),
            LiveStatusRecord(
                machine_id=machine_id,
                collected_at=start + timedelta(minutes=3),
                state="stopped",
                status="Weft",
                rpm=490.0,
                efficiency=88.0,
                bits={"weft": 1},
                data={"run_time": 901.0, "stop_time": 63.0, "stop_shift": 4},
                setup={"style": "1210"},
            ),
            LiveStatusRecord(
                machine_id=machine_id,
                collected_at=start + timedelta(minutes=4),
                state="run",
                status="Run",
                rpm=505.0,
                efficiency=89.0,
                bits={},
                data={"run_time": 902.0, "stop_time": 63.0, "stop_shift": 4},
                setup={"style": "1210"},
            ),
        ]
    )
    db.commit()


def test_collects_once_per_day_and_uses_history(db, monkeypatch):
    monkeypatch.setattr(daily_collection, "fetch_live", lambda ip, timeout=0: _live())
    _seed_history(db, 1)

    run = daily_collection.collect_daily_data(db, DAY)
    assert run.status == "partial"  # 00002 ok, 00003 sem IP
    assert run.success_count == 2
    assert run.retry_count == 1

    rows = db.execute(select(DailyLoomData)).scalars().all()
    assert len(rows) == 2
    row = next(r for r in rows if r.mac_name == "00001")
    assert row.source == "history"
    assert row.rpm == pytest.approx((500 + 490 + 490 + 505) / 4)
    assert row.efficiency == pytest.approx((90 + 88.5 + 88 + 89) / 4)
    assert row.trama_stops == 1
    assert row.trama_stops_min == pytest.approx(3.0)
    assert row.total_stop_ct == 4

    # Segunda execucao nao cria outra execucao nem duplica linhas.
    again = daily_collection.collect_daily_data(db, DAY)
    assert again.id == run.id
    assert db.query(DailyCollectionRun).count() == 1
    assert db.query(DailyLoomData).count() == 2


def test_offline_loom_goes_to_retry_queue_then_collects(db, monkeypatch):
    monkeypatch.setattr(
        daily_collection, "fetch_live", lambda ip, timeout=0: error_status(100)
    )
    run = daily_collection.collect_daily_data(db, DAY)
    assert run.status == "failed"
    assert run.retry_count == 3  # 00001 e 00002 fora do ar; 00003 sem IP

    item = db.execute(
        select(DailyCollectionItem).where(DailyCollectionItem.mac_name == "00002")
    ).scalar_one()
    assert item.in_retry_queue is True
    assert "Power_off" in item.error_reason

    monkeypatch.setattr(daily_collection, "fetch_live", lambda ip, timeout=0: _live(rpm=610.0))
    retried = daily_collection.retry_pending(db, DAY, respect_interval=False)
    assert retried.status == "partial"
    assert retried.retry_count == 1  # only 00003 (sem IP) remains

    row = db.execute(
        select(DailyLoomData).where(DailyLoomData.mac_name == "00002")
    ).scalar_one()
    assert row.rpm == 610.0
    assert row.source == "live"


def test_agg_shift_has_priority_for_stop_breakdown(db, monkeypatch):
    monkeypatch.setattr(daily_collection, "fetch_live", lambda ip, timeout=0: _live())
    stop_ct = [1, 2, 0, 0, 0, 3, 0, 0, 0, 0, 4, 0]
    stop_tm = [2.0, 4.0, 0.0, 0.0, 0.0, 6.0, 0.0, 0.0, 0.0, 0.0, 8.0, 0.0]
    db.add(
        AggShift(
            shift_id=f"{DAY:%Y.%m.%d}.0",
            machine_id=1,
            style="ABC",
            seisan_1=100.0,
            seisan_2=50.0,
            seisan_3=None,
            run_tm=420.0,
            stop_ttm=20.0,
            stop_ct=stop_ct,
            stop_tm=stop_tm,
        )
    )
    db.commit()

    daily_collection.collect_daily_data(db, DAY)
    row = db.execute(
        select(DailyLoomData).where(DailyLoomData.mac_name == "00001")
    ).scalar_one()
    assert row.source == "agg_shift"
    assert row.style == "ABC"
    assert row.production == 150.0
    assert row.trama_stops == 3
    assert row.trama_stops_min == 6.0
    assert row.urdume_stops == 3
    assert row.urdume_stops_min == 6.0
    assert row.outros_stops == 4
    assert row.outros_stops_min == 8.0
    assert row.total_stop_ct == 10
